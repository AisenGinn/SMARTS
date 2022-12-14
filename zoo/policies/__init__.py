import sys
import os
import importlib.util
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Any, Dict

from smarts.core.agent_interface import AgentInterface, AgentType
from smarts.core.controllers import ActionSpaceType
from smarts.zoo.agent_spec import AgentSpec
from smarts.env.multi_scenario_env import resolve_agent_interface
from smarts.zoo.registry import make, register

from .keep_lane_agent import KeepLaneAgent
from .non_interactive_agent import NonInteractiveAgent
from .waypoint_tracking_agent import WaypointTrackingAgent

register(
    locator="non-interactive-agent-v0",
    entry_point=lambda **kwargs: AgentSpec(
        interface=AgentInterface(waypoints=True, action=ActionSpaceType.TargetPose),
        agent_builder=NonInteractiveAgent,
        agent_params=kwargs,
    ),
)

register(
    locator="keep-lane-agent-v0",
    entry_point=lambda **kwargs: AgentSpec(
        interface=AgentInterface.from_type(AgentType.Laner, max_episode_steps=20000),
        agent_builder=KeepLaneAgent,
    ),
)

register(
    locator="waypoint-tracking-agent-v0",
    entry_point=lambda **kwargs: AgentSpec(
        interface=AgentInterface.from_type(AgentType.Tracker, max_episode_steps=300),
        agent_builder=WaypointTrackingAgent,
    ),
)


def klws_entrypoint(speed):
    from .keep_left_with_speed_agent import KeepLeftWithSpeedAgent

    return AgentSpec(
        interface=AgentInterface.from_type(
            AgentType.LanerWithSpeed, max_episode_steps=20000
        ),
        agent_params={"speed": speed * 0.01},
        agent_builder=KeepLeftWithSpeedAgent,
    )


register(locator="keep-left-with-speed-agent-v0", entry_point=klws_entrypoint)

social_index = 0
replay_save_dir = "./replay"
replay_read = False


def replay_entrypoint(
    save_directory,
    id,
    wrapped_agent_locator,
    wrapped_agent_params=None,
    read=False,
):
    if wrapped_agent_params is None:
        wrapped_agent_params = {}
    from .replay_agent import ReplayAgent

    internal_spec = make(wrapped_agent_locator, **wrapped_agent_params)
    global social_index
    global replay_save_dir
    global replay_read
    spec = AgentSpec(
        interface=internal_spec.interface,
        agent_params={
            "save_directory": replay_save_dir,
            "id": f"{id}_{social_index}",
            "internal_spec": internal_spec,
            "wrapped_agent_params": wrapped_agent_params,
            "read": replay_read,
        },
        agent_builder=ReplayAgent,
    )
    social_index += 1
    return spec


register(locator="replay-agent-v0", entry_point=replay_entrypoint)


def human_keyboard_entrypoint(*arg, **kwargs):
    from .human_in_the_loop import HumanKeyboardAgent

    spec = AgentSpec(
        interface=AgentInterface.from_type(
            AgentType.StandardWithAbsoluteSteering, max_episode_steps=3000
        ),
        agent_builder=HumanKeyboardAgent,
    )
    return spec


register(locator="human-in-the-loop-v0", entry_point=human_keyboard_entrypoint)


def load_config(path):
    import yaml

    config = None
    if path.exists():
        with open(path, "r") as file:
            config = yaml.safe_load(file)
    return config


root_path = str(Path(__file__).absolute().parents[2])


def competition_entry(**kwargs):
    policy_path = kwargs.get("policy_path", None)
    comp_env_path = str(
        os.path.join(root_path, "competition_env")
    )  # folder contains all competition environment
    sub_env_path = os.path.join(
        comp_env_path, f"{Path(policy_path).name}"
    )  # folder contains single competition environment
    req_file = os.path.join(
        policy_path, "requirements.txt"
    )  # path of the requiremnet file

    if Path(sub_env_path).exists():
        shutil.rmtree(sub_env_path)
    Path.mkdir(Path(sub_env_path), parents=True, exist_ok=True)

    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-t",
                sub_env_path,
                "-r",
                req_file,
            ]
        )
        sys.path.append(sub_env_path)
    except:
        logging.error(
            f"Failed to install requirement for Competition Agent in folder {Path(policy_path).name}"
        )
        raise

    # Remove all potentially exist duplicated policy_path in sys.path and insert policy_path in front
    # This is to avoid other paths in sys.path that contains policy.py been searched before policy_path
    while policy_path in sys.path:
        sys.path.remove(policy_path)

    sys.path.insert(0, policy_path)

    # import policy module
    policy_file_path = str(os.path.join(policy_path, "policy.py"))
    policy_spec = importlib.util.spec_from_file_location(
        "competition_policy", policy_file_path
    )
    policy_module = importlib.util.module_from_spec(policy_spec)
    sys.modules["competition_policy"] = policy_module
    if policy_spec:
        policy_spec.loader.exec_module(policy_module)

    policy = policy_module.Policy()
    wrappers = policy_module.submitted_wrappers()

    from .competition_agent import CompetitionAgent

    def env_wrapper(env):
        import gym

        env = gym.Wrapper(env)
        for wrapper in wrappers:
            env = wrapper(env)

        return env

    # callback function used in CompetitionAgent to delete all related path, modules and dependencies
    def at_exit(policy_dir, all_env_dir, sub_env_dir, remove_all_env=False):
        shutil.rmtree(str(sub_env_dir))
        while sub_env_dir in sys.path:
            sys.path.remove(sub_env_dir)
        while policy_dir in sys.path:
            sys.path.remove(policy_dir)
        for key, module in list(sys.modules.items()):
            if "__file__" in dir(module):
                module_path = module.__file__
                if module_path and (
                    policy_dir in module_path or sub_env_dir in module_path
                ):
                    sys.modules.pop(key)
        if remove_all_env:
            shutil.rmtree(str(all_env_dir), ignore_errors=True)

    config = load_config(Path(os.path.join(policy_path, "config.yaml")))

    spec = AgentSpec(
        interface=resolve_agent_interface(
            img_meters=int(config["img_meters"]),
            img_pixels=int(config["img_pixels"]),
            action_space="TargetPose",
        ),
        agent_params={
            "policy_path": policy_path,
            "policy": policy,
            "at_exit": at_exit,
        },
        adapt_env=env_wrapper,
        agent_builder=CompetitionAgent,
    )

    # delete competition policy module and remove related path
    while (
        policy_path in sys.path
    ):  # use while loop to prevent duplicated policy_path in sys.path inserted in policy.py by user
        sys.path.remove(policy_path)

    # remove all modules related to policy_path
    for key, module in list(sys.modules.items()):
        if "__file__" in dir(module):
            module_path = module.__file__
            if module_path and (policy_path in module_path):
                sys.modules.pop(key)

    del policy_module

    return spec


register(
    "competition_agent-v0",
    entry_point=competition_entry,
    policy_path=os.path.join(root_path, "competition/track1/submission"),
)
