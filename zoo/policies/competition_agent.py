from distutils.command.config import config
import subprocess
import sys
import os
import gym

from pathlib import Path
from smarts.core.agent import Agent

class CompetitionAgent(Agent):
    def __init__(self, policy_path) :
        root_path = Path(__file__).absolute().parents[2]
        req_file = os.path.join(root_path, "competition/track1/submission/requirements.txt")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
        except:
            print("Failed to install requirement for Competition Agent")
        
        sys.path.insert(0, policy_path)
        from policy import Policy, submitted_wrappers
        
        self._policy = Policy()
        self._wrapper = submitted_wrappers()

    def act(self, obs):
        return self._policy.act(obs)

    def wrap_env(self, env):
        test_env = gym.Wrapper(env)
        for wrapper in self._wrapper:
            test_env = wrapper(test_env)
        
        return test_env