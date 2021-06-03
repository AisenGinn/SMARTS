# MIT License
#
# Copyright (C) 2021. Huawei Technologies Co., Ltd. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import copy
import gym
from collections import deque
from typing import Deque, Dict, Tuple, Union
from smarts.core import sensors


class FrameStack(gym.Wrapper):
    """ By default, this wrapper will stack 3 consecutive frames as an agent observation"""

    def __init__(self, env: gym.Env, num_stack: int = 3):
        super(FrameStack, self).__init__(env)
        self.num_stack = num_stack
        self.frames = {
            key: deque(maxlen=self.num_stack) for key in self.env.agent_specs.keys()
        }

    def _get_observations(
        self, frame: sensors.Observation
    ) -> Dict[str, Deque[sensors.Observation]]:
        """Update and return frames stack with given latest single frame."""

        new_frames = dict.fromkeys(frame)

        for agent_id, observation in frame.items():
            self.frames[agent_id].append(observation)
            frames_list = list(self.frames[agent_id])
            new_frames[agent_id] = copy.deepcopy(frames_list)

        return new_frames

    def step(
        self, agent_actions: Dict
    ) -> Tuple[
        Dict[str, Deque[sensors.Observation]],
        Dict[str, float],
        Dict[str, bool],
        Dict[str, Dict[str, Union[float, sensors.Observation]]],
    ]:

        env_observations, rewards, dones, infos = super(FrameStack, self).step(
            agent_actions
        )

        return self._get_observations(env_observations), rewards, dones, infos

    def reset(self) -> Dict[str, Deque[sensors.Observation]]:
        env_observations = super(FrameStack, self).reset()
        for agent_id, observation in env_observations.items():
            [
                self.frames[agent_id].append(observation)
                for _ in range(self.num_stack - 1)
            ]
        return self._get_observations(env_observations)
