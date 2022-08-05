.. _extras_options:

Extras Installation Options
===========================

==========
camera-obs
==========

This option install [camera-obs] version of python package with the panda3D dependencies, and is used to render camera sensor observations in your simulations.
For detail documentation for obserevations, please refer to `[SMARTS/docs/sim/observatoins.rst] <https://github.com/huawei-noah/SMARTS/blob/master/docs/sim/observations.rst>`_.

===
dev
===

This option includes black, grpcio-tools, isort, pre-commit, pylint, pytype packages, which is mainly used for developing and formating.

===
doc
===

This option contains sphinx related packages, which are used for documentation.

======
extras
======

This option contains pynput package which is used by human-keyboard Agent, which allows the user to to control and monitor input devices.
For detail implementation of human-keyboard Agent, please refer to `['SMARTS/zoo/policies/human_in_the_loop.py'] <https://github.com/huawei-noah/SMARTS/blob/master/zoo/policies/human_in_the_loop.py>`_.

=====
rllib
=====

This option contains python opencv and ray[rllib] packages, which is used for reinforcement learning in SMARTS.
You can find the detailed explanation of rllib at `['SMARTS/docs/sim/rllib_in_smarts.rst'] <https://github.com/huawei-noah/SMARTS/blob/master/docs/sim/rllib_in_smarts.rst>`_,
and how to use rllib to train agent at `['SMARTS/ultra/docs/rllib.md'] <https://github.com/huawei-noah/SMARTS/blob/master/ultra/docs/rllib.md>`_.

===
ros
===

This option installs catkin and ROS package in order to create a catkin workspace for a ROS (v1) node that wraps/drives a SMARTS simulation.
For detail information, please refer to `['SMARTS/smarts/ros/README.md'] <https://github.com/huawei-noah/SMARTS/blob/master/smarts/ros/README.md>`_.

====
test
====

This option installs ipykernal, jupyter-client, and pytest related packages. Which is mainly used for testing the examples and the learning performance.
The detail implementation of the tests can be found in `['SMARTS/examples/tests'] <https://github.com/huawei-noah/SMARTS/tree/master/examples/tests>`_.

=====
torch
=====

This option import pytorch package which used for learning and training.

=====
train
=====

This option import tensorflow package which used for learnign and training.

=====
waymo
=====

This option installs the waymo motion dataset. SMARTS supports importing traffic histories from the Waymo motion dataset to replay in a SMARTS simulation.
To use this dataset, please refer to `['SMARTS/scenarios/waymo/README.md'] <https://github.com/huawei-noah/SMARTS/blob/master/scenarios/waymo/README.md>`_.

=========
opendrive
=========

This option installs opendrive2lanelet, which is mainly used for different scenarios.