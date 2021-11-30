import os

# Set pythonhashseed
os.environ["PYTHONHASHSEED"] = "0"
# Silence the logs of TF
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

# The below is necessary for starting Numpy generated random numbers
# in a well-defined initial state.
import numpy as np

np.random.seed(123)

# The below is necessary for starting core Python generated random numbers
# in a well-defined state.
import random as python_random

python_random.seed(123)

# The below set_seed() will make random number generation
# in the TensorFlow backend have a well-defined initial state.
# For further details, see:
# https://www.tensorflow.org/api_docs/python/tf/random/set_seed
import tensorflow as tf

tf.random.set_seed(123)

# --------------------------------------------------------------------------

import signal
import sys
import warnings
from datetime import datetime
from pathlib import Path

import yaml

from examples.auto_drive.agent import behaviour, vehicle_gae
from examples.auto_drive.env import traffic
from examples.auto_drive.rl import mode
from examples.auto_drive.rl.ppo_gae import ppo_gae


def main(config, modeldir, logdir):

    print("[INFO] Train")
    save_interval = config.get("save_interval", 20)
    run_mode = mode.Mode(config["mode"])  # Mode: Evaluation or Testing

    # Traning parameters
    n_steps = config["n_steps"]
    max_traj = config["max_traj"]

    # Create env
    print("[INFO] Creating environments")
    env = traffic.make_traffic_env(config, config["seed"])

    # TODO: Need agent to policy mapping
    print("------------------------------------------")
    print("HARDCODE WARNING !!!!!!!!!!")
    if hasattr(env.action_space, "n"):
        config["action_dim"] = env.action_space.n
    config["observation_dim"] = env.observation_space["Tiger1"].shape
    print("observation dim = ", config["observation_dim"])
    print("action dim =", config["action_dim"])
    print("------------------------------------------")

    # Create agent
    print("[INFO] Creating agents")
    all_agents = {
        name: vehicle_gae.VehicleGAE(name, config) for name in env.agent_specs.keys()
    }

    # Create model
    print("[INFO] Creating model")
    policy = ppo_gae.PPOGAE(
        name=behaviour.Behaviour.CRUISER,
        config=config,
        agent_ids=env.agent_specs.keys(),
        seed=config["seed"] + 1,
        modeldir=modeldir,
        logdir=logdir,
    )

    def interrupt(*args):
        nonlocal run_mode
        nonlocal policy
        if run_mode == mode.Mode.TRAIN:
            policy.save(-1)
        env.close()
        print("Interrupt key detected.")
        sys.exit(0)

    # Catch keyboard interrupt and terminate signal
    signal.signal(signal.SIGINT, interrupt)

    print("[INFO] Batch loop")
    states_t = env.reset()
    episode = 0
    steps_t = 0
    episode_reward = 0
    flag_crash = False
    for traj_num in range(max_traj):
        [agent.reset() for _, agent in all_agents.items()]
        active_agents = {}

        print(f"[INFO] New batch data collection {traj_num}/{max_traj}")
        for cur_step in range(n_steps):

            # Update all agents which were active in this batch
            active_agents.update({agent_id: True for agent_id, _ in states_t.items()})

            # Given state, predict action and value
            logit_t = {}
            action_t = {}
            value_t = {}
            logprobability_t = {}

            logit, action = policy.actor(obs=states_t, train=run_mode)
            value = policy.critic(states_t)
            logit_t.update(logit)
            action_t.update(action)
            value_t.update(value)

            for agent_id, logit in logit_t.items():
                logprobability_t[agent_id] = ppo_gae.logprobabilities(
                    logit, [action_t[agent_id]]
                ).numpy()[0]

            # Sample action from a distribution
            try:
                next_states_t, reward_t, done_t, _ = env.step(action_t)
            except:
                # To counter tracii error
                print(
                    f"   Simulation crashed and reset. Cur_Step: {cur_step}. Step: {steps_t}."
                )
                step = traj_num * n_steps + cur_step
                policy.save(-1 * step)
                new_env = traffic.make_traffic_env(config, config["seed"] + step)
                env = new_env
                next_states_t = env.reset()
                states_t = next_states_t
                flag_crash = True
                break

            steps_t += 1

            # Store observation, action, and reward
            for agent_id, _ in states_t.items():
                all_agents[agent_id].add_transition(
                    observation=states_t[agent_id],
                    action=action_t[agent_id],
                    reward=reward_t[agent_id],
                    value=value_t[agent_id],
                    logprobability=logprobability_t[agent_id],
                    done=int(done_t[agent_id]),
                )
                episode_reward += reward_t[agent_id]
                if done_t[agent_id] == 1:
                    # Remove done agents
                    del next_states_t[agent_id]
                    # Print done agents
                    print(
                        f"   Done: {agent_id}. Cur_Step: {cur_step}. Step: {steps_t}."
                    )

            # Reset when episode completes
            if done_t["__all__"]:
                # Next episode
                next_states_t = env.reset()
                episode += 1

                # Log rewards
                print(
                    f"   Episode: {episode}. Cur_Step: {cur_step}. "
                    f"Episode reward: {episode_reward}."
                )
                policy.write_to_tb([("episode_reward", episode_reward, episode)])

                # Reset counters
                episode_reward = 0
                steps_t = 0

            # Assign next_states to states
            states_t = next_states_t

        # If env crash due to tracii error, reset env and skip to next trajectory.
        if flag_crash == True:
            flag_crash = False
            continue

        # Skip the remainder if evaluating
        if run_mode == mode.Mode.EVALUATE:
            continue

        # Compute and store last state value
        for agent_id in active_agents.keys():
            if done_t.get(agent_id, None) == 0:  # Agent not done yet
                next_value_t = policy.critic({agent_id: next_states_t[agent_id]})
                all_agents[agent_id].add_last_transition(value=next_value_t[agent_id])
            else:  # Agent is done
                all_agents[agent_id].add_last_transition(value=np.float32(0))

            # Compute generalised advantages and return
            all_agents[agent_id].finish_trajectory()

        # Elapsed steps
        step = (traj_num + 1) * n_steps

        print("[INFO] Training")
        # Run multiple gradient ascent on the samples.
        active_predators = [all_agents[agent_id] for agent_id in active_agents.keys()]

        for policy, agents in [
            (policy, active_predators),
        ]:
            update_actor(
                policy,
                agents,
                config["actor_train_epochs"],
                config["target_kl"],
                config["clip_ratio"],
                config["grad_batch"],
            )
            update_critic(
                policy,
                agents,
                config["critic_train_epochs"],
                config["grad_batch"],
            )

        # Save model
        if traj_num % save_interval == 0:
            print("[INFO] Saving model")
            policy.save(step)

    # Close env
    env.close()


def update_actor(policy, agents, iterations, target_kl, clip_ratio, grad_batch):
    for agent in agents:
        for _ in range(iterations):
            kl = ppo_gae.train_actor(
                policy=policy, agent=agent, clip_ratio=clip_ratio, grad_batch=grad_batch
            )
            if kl > 1.5 * target_kl:
                # Early Stopping
                break


def update_critic(policy, agents, iterations, grad_batch):
    for agent in agents:
        for _ in range(iterations):
            ppo_gae.train_critic(policy=policy, agent=agent, grad_batch=grad_batch)


if __name__ == "__main__":
    config_yaml = (Path(__file__).absolute().parent).joinpath("config.yaml")
    with open(config_yaml, "r") as file:
        config = yaml.load(file, Loader=yaml.FullLoader)

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
        # raise SystemError("GPU device not found")

    name = "ppo_gae"
    time = datetime.now().strftime("%Y_%m_%d_%H_%M")
    logdir = (
        (Path(__file__).absolute().parents[2])
        .joinpath("logs")
        .joinpath(name)
        .joinpath(time)
    )
    modeldir = (
        (Path(__file__).absolute().parents[2])
        .joinpath("models")
        .joinpath(name)
        .joinpath(time)
    )

    main(config=config[name], modeldir=modeldir, logdir=logdir)