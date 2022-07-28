# Offline Reinforcement Learning

## Objective
Objective is to train a single **offline** reinforcement learning (RL) policy capable of controlling single-agent or multi-agent to complete different tasks in various scenarios. In each scenario the ego-agents must drive towards their respective goal locations. 

## Data and RL Model
1. For offline RL training, use Waymo datasets.
1. Waymo utilities from https://github.com/huawei-noah/SMARTS/tree/saul/waymo-extraction/smarts/waymo, can be used to  
   + to browse Waymo dataset, and 
   + to extract Waymo data into SMARTS observations.
1. Trained RL model should accept multi-agent observation of the format `Dict[agent_name: agent_observation]`. Observation space for each agent is `smarts.core.sensors.Observation`. For more details on the contents of `Observation` class, see https://github.com/huawei-noah/SMARTS/blob/comp-1/smarts/core/sensors.py#L186
1. Each agent's mission goal is given in the observation returned at each time step. The mission goal could be accessed as `observation.ego_vehicle_state.mission.goal.position` which gives an `(x, y, z)` map coordinate of the goal location.
1. Trained RL model should output multi-agent action of the format `Dict[agent_name: agent_action]`. Action space for each agent is `smarts.core.controllers.ActionSpaceType.TargetPose` which is a sequence of `[x-coordinate, y-coordinate, heading, and time-delta]`. Use `time-delta=0.1`.

## Process Overview
### Folder Structure
1. The submitted folder structure for Track-2 should be as follows. The folder and file names are to be maintained.
    ```text
    track2                       # Main folder.
    ├── train                    # Contains code to train an offline RL model.
    │   ├── train.py             # Primary training script for training a new model.
    │   ├── ...                  # Other necessary training files.
    |   .
    |   .
    |   .
    ├── submission                       
    |    ├── policy.py            # A policy with an act method, wrapping the saved RL model.
    |    ├── requirements.txt     # Dependencies needed to run the RL model.
    |    ├── explanation.md       # Brief explanation of the key techniques used in developing the submitted model.
    |    ├── ...                  # Other necessary files for inference.
    |    .
    |    .
    |    .
    └── Dockerfile                # Dockerfile to build and run the RL training code.
    ```

### Train Folder
1. Use `python3.8` to develop your model.
1. The `track2/train/train.py` code should be capable of reading in new offline data fed in by the competition organizers, train a new RL model offline from scratch, and automatically save the newly trained model into the `track2/submission` folder.

### Submission Folder
1. On completion of training, the `track2/train/train.py` code should automatically save the trained RL model into the `track2/submission` folder. Place all necessary files to run the saved model for inference inside the `track2/submission` folder. 
1. Besides the saved RL model, the files named `policy.py`, `requirements.txt`, and `explanation.md`, must be included within this folder. Its contents are identical to that of Track-1 and they are explained at 
    + [Policy](../track1/submission/README.md#Policy)
    + [Wrappers](../track1/submission/README.md#Wrappers)
    + [Requirements](../track1/submission/README.md#Requirements)
    + [Explanation](../track1/submission/README.md#Explanation)

### Dockerfile, DockerHub, Retraining, and Evaluation
1. The submitted `track2` folder must contain a `track2/Dockerfile`. 
1. Build upon the template Dockerfile provided at `track2/Dockerfile`. Do not modify sections labelled as `[Do not modify]`. Feel free to use any desired base image, install any additional packages, etc.
1. The Dockerfile must start training upon execution of `docker run` command, hence do not change the `ENTRYPOINT` command. Avoid using `CMD` as it might be superseeded by external commands when running the container.
1. Build the docker image locally and push the built docker image to [DockerHub](https://hub.docker.com/). 
    ```bash
    $ cd <path>/SMARTS/competition/track2
    $ docker build \
        --file=./Dockerfile \
        --network=host \ 
        --tag=<username/imagename:version>
        .
    ```
1. Provide the link to the DockerHub image in `track2/submission/explanation.md` file.
1. After uploading your Docker image to DockerHub, proceed to submitting the entire `track2` folder to Codalab Track2. 
1. During evaluation, the docker image will be pulled and run with the following commands. 
    ```bash
    $ docker pull <username/imagename:version>
    $ docker run --rm -it \
        --gpus=all \
        --volume=<path>/offline_data:/offline_data
        --volume=<path>/track2/submission:/track2/submission 
        <username/imagename:version>
    ```
1. Training a new RL model should start once the above command is executed.
1. New offline data is made available to the container via a mapped volume at `/offline_data` directory.
1. The `/offline_data` directory contains selected offline datasets.
1. Inside the container, on completion of training,  the trained model should be saved in `/track2/submission` folder such that calling `/track2/submission/policy.py::Policy.act(obs)` with a SMARTS observation returns an action.
1. The `/track2/submission` folder will be mapped out from the container and then evaluated by the same evaluation script as that of Track-1. See evaluation [README.md](../evaluation/README.md).
1. During development, it is strongly suggested for you to submit your zipped `track2/submission` folder to the Validation Track in Codalab, to verify that the evaluation works without errors.
1. Finally, the offline RL training code in `/track2/train` directory will be manually scrutinised. 

### Submit to Codalab
+ Zip the entire `track2` folder. 
    + If the `track2` folder is located at `<path>/SMARTS/competition/track2`, then run the following to easily create a zipped folder. 
        ```bash
        $ cd <path>/SMARTS/competition
        $ make track2_submission.zip 
        ```
+ Upload the `track2.zip` to CodaLab.
    + Go to the [CodaLab competition page](https://codalab.lisn.upsaclay.fr/).
    + Click `My Competitions -> Competitions I'm In`.
    + Select the SMARTS competition.
    + Click `Participate -> Submit/View Results -> Submit`
    + Upload the zipped folder.