# To start Numpy generated random numbers in a well-defined initial state.
import numpy as np

np.random.seed(123)

# To start core Python generated random numbers in a well-defined state.
import random as python_random

python_random.seed(123)

# set_seed() will make random number generation in the TensorFlow backend have
# a well-defined initial state.
# https://www.tensorflow.org/api_docs/python/tf/random/set_seed
import tensorflow as tf

tf.random.set_seed(123)

# -----------------------------------------------------------------------------

import collections
import logging
import os
import pathlib
import re
import warnings
from datetime import datetime

import dreamerv2 as dv2
import dreamerv2.api as dv2_api
import dreamerv2.agent as dv2_agent
import dreamerv2.common as dv2_common
import numpy as np
import rich.traceback
from env import single_agent
from ruamel.yaml import YAML

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"  # Silence the TF logs
logging.getLogger().setLevel("ERROR")
warnings.filterwarnings("ignore", ".*box bound precision lowered.*")
rich.traceback.install()
yaml = YAML(typ="safe")


def main():
    # Load env config
    name = "dreamerv2"
    config_env = yaml.load(
        (pathlib.Path(__file__).absolute().parent / "config.yaml").read_text()
    )
    config_env = config_env[name]

    # Load dreamerv2 config
    config_dv2 = dv2.api.defaults

    # Setup tensorflow
    # tf.config.experimental_run_functions_eagerly(not config.jit)
    # assert config.precision in (16, 32), config.precision
    # if config.precision == 16:
    #     from tensorflow.keras.mixed_precision import experimental as prec
    #     prec.set_policy(prec.Policy("mixed_float16"))

    # Setup GPU
    gpus = tf.config.list_physical_devices("GPU")
    if gpus:
        try:
            # Currently, memory growth needs to be the same across GPUs
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
            logical_gpus = tf.config.list_logical_devices("GPU")
            print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
        except RuntimeError as e:
            # Memory growth must be set before GPUs have been initialized
            print(e)
    else:
        warnings.warn(
            f"Not configured to use GPU or GPU not available.",
            ResourceWarning,
        )

    # Create env
    config_env["scenarios_dir"] = pathlib.Path(__file__).absolute().parents[2] / "scenarios"
    gen_env = single_agent.gen_env(config_env, config_env["seed"])

    # Train or evaluate
    if config_env["mode"] == "train":
        # Setup logdir
        time = datetime.now().strftime("%Y_%m_%d_%H_%M")
        logdir = pathlib.Path(__file__).absolute().parents[0] / "logs" / name / time
        config_dv2 = config_dv2.update(
            {
                "logdir": logdir,
                "log_every": 1e4,
                "eval_every": 1e5,  # Save interval (steps)
                "eval_eps": 1,
                "train_every": 5,                
                "task": None,
                "prefill": 10000,
                "replay.minlen": 20,
                "replay.maxlen": 50,
            }
        )
    elif config_env["mode"] == "evaluate":
        config_dv2.update(
            {
                "logdir": config_env["logdir_evaluate"],
                "log_every": 1e8, # No logging needed
                "eval_every": 0,  # Save interval (steps)
                "eval_eps": 1e8, # Evaluate forever
                "train_every": 1e8, # No training needed            
                "task": None,
                "prefill": 10000,
                "replay.minlen": 20,
                "replay.maxlen": 50,
            }
        )
    else:
        raise KeyError(f'Expected \'train\' or \'evaluate\', but got {config_env["mode"]}.')

    # Train or evaluate dreamerv2 with env
    train(config_dv2, gen_env)

def wrap_env(env, config):
    env = dv2.common.GymWrapper(env)
    env = dv2.common.ResizeImage(env)
    if hasattr(env.act_space["action"], "n"):
        env = dv2.common.OneHotAction(env)
    else:
        env = dv2.common.NormalizeAction(env)
    env = dv2.common.TimeLimit(env, config.time_limit)
    return env

def train(config, gen_env):
    logdir = pathlib.Path(config.logdir).expanduser()
    logdir.mkdir(parents=True, exist_ok=True)
    config.save(logdir / "config.yaml")
    print(config, "\n")
    print("Logdir", logdir)

    train_replay = dv2.common.Replay(logdir / "train_episodes", **config.replay)
    eval_replay = dv2.common.Replay(
        logdir / "eval_episodes",
        **dict(
            capacity=config.replay.capacity // 10,
            minlen=1,
            maxlen=config.dataset.length,
        ),
    )
    step = dv2.common.Counter(train_replay.stats["total_steps"])
    outputs = [
        dv2.common.TerminalOutput(),
        dv2.common.TensorBoardOutput(logdir),
    ]
    logger = dv2.common.Logger(step, outputs, multiplier=config.action_repeat)
    metrics = collections.defaultdict(list)

    should_train = dv2.common.Every(config.train_every)
    should_log = dv2.common.Every(config.log_every)
    should_video_train = dv2.common.Every(config.eval_every)
    should_video_eval = dv2.common.Every(config.eval_every)
    should_expl = dv2.common.Until(config.expl_until)

    def per_episode(ep, mode):
        length = len(ep["reward"]) - 1
        score = float(ep["reward"].astype(np.float64).sum())
        print(f"{mode.title()} episode has {length} steps and return {score:.1f}.")
        logger.scalar(f"{mode}_return", score)
        logger.scalar(f"{mode}_length", length)
        for key, value in ep.items():
            if re.match(config.log_keys_sum, key):
                logger.scalar(f"sum_{mode}_{key}", ep[key].sum())
            if re.match(config.log_keys_mean, key):
                logger.scalar(f"mean_{mode}_{key}", ep[key].mean())
            if re.match(config.log_keys_max, key):
                logger.scalar(f"max_{mode}_{key}", ep[key].max(0).mean())
        should = {"train": should_video_train, "eval": should_video_eval}[mode]
        if should(step):
            for key in config.log_keys_video:
                logger.video(f"{mode}_policy_{key}", ep[key])
        replay = dict(train=train_replay, eval=eval_replay)[mode]
        logger.add(replay.stats, prefix=mode)
        logger.write()

    print("Create envs.")
    if config.envs_parallel == "none":
        train_envs = [wrap_env(next(gen_env), config)]
        eval_envs = [wrap_env(next(gen_env), config)]
    act_space = train_envs[0].act_space
    obs_space = train_envs[0].obs_space
    train_driver = dv2.common.Driver(train_envs)
    train_driver.on_episode(lambda ep: per_episode(ep, mode="train"))
    train_driver.on_step(lambda tran, worker: step.increment())
    train_driver.on_step(train_replay.add_step)
    train_driver.on_reset(train_replay.add_step)
    eval_driver = dv2.common.Driver(eval_envs)
    eval_driver.on_episode(lambda ep: per_episode(ep, mode="eval"))
    eval_driver.on_episode(eval_replay.add_episode)

    prefill = max(0, config.prefill - train_replay.stats["total_steps"])
    if prefill:
        print(f"Prefill dataset ({prefill} steps).")
        random_agent = dv2.common.RandomAgent(act_space)
        train_driver(random_agent, steps=prefill, episodes=1)
        eval_driver(random_agent, episodes=1)
        train_driver.reset()
        eval_driver.reset()

    print("Create agent.")
    train_dataset = iter(train_replay.dataset(**config.dataset))
    report_dataset = iter(train_replay.dataset(**config.dataset))
    eval_dataset = iter(eval_replay.dataset(**config.dataset))
    agnt = dv2.agent.Agent(config, obs_space, act_space, step)
    train_agent = dv2.common.CarryOverState(agnt.train)
    train_agent(next(train_dataset))
    if (logdir / "variables.pkl").exists():
        agnt.load(logdir / "variables.pkl")
    else:
        print("Pretrain agent.")
        for _ in range(config.pretrain):
            train_agent(next(train_dataset))
    train_policy = lambda *args: agnt.policy(
        *args, mode="explore" if should_expl(step) else "train"
    )
    eval_policy = lambda *args: agnt.policy(*args, mode="eval")

    def train_step(tran, worker):
        if should_train(step):
            for _ in range(config.train_steps):
                mets = train_agent(next(train_dataset))
                [metrics[key].append(value) for key, value in mets.items()]
        if should_log(step):
            for name, values in metrics.items():
                logger.scalar(name, np.array(values, np.float64).mean())
                metrics[name].clear()
            logger.add(agnt.report(next(report_dataset)), prefix="train")
            logger.write(fps=True)

    train_driver.on_step(train_step)

    while step < config.steps:
        logger.write()
        print("Start evaluation.")
        logger.add(agnt.report(next(eval_dataset)), prefix="eval")
        eval_driver(eval_policy, episodes=config.eval_eps)
        print("Start training.")
        train_driver(train_policy, steps=config.eval_every)
        agnt.save(logdir / "variables.pkl")
    for env in train_envs + eval_envs:
        try:
            env.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
