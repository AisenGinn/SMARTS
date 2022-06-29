from turtle import backward
import moviepy.editor as mpy
import json
import os
import os.path
import pkgutil
import shutil
import subprocess
import tempfile
from io import StringIO
from typing import List, Optional, Tuple, Union

import numpy as np

from gym import error, logger

def touch(path:str):
    open(path, "a").close()

class VideoRecorder:
    """
    VideoRecorder renders a nice movie of a rollout, frame by frame
    """
    def __init__(self, 
                env, path: Optional[str] = None,
                metadata: Optional[dict] = None,
                enabled: bool = True,
                base_path: Optional[str] = None,):
        
        modes = env.metadata.get("render_modes",[])
        backward_compatible_mode = env.metadata.get("render.modes",[])
        if len(modes) == 0 and len(backward_compatible_mode) > 0:
            logger.deprecation(
                '`env.metadata["render.modes"] is marked as deprecated and will be replaced '
                'with `env.metadata["render_modes"]` see https://github.com/openai/gym/pull/2654 for more details'
            )
            modes = backward_compatible_mode

        self._async = env.metadata.get("semantics.async")
        self.enabled = enabled
        self._closed = False

        self.ansi_mode = False
        if "rgb_array" not in modes:
            if "ansi" in modes:
                self.ansi_mode = True
            else:
                logger.info(
                    f'Disabling video recorder because {env} neither supports video mode "rgb_array" nor "ansi".'
                )
                # Whoops, turns out we shouldn't be enabled after all
                self.enabled = False
        # Don't bother setting anything else if not enabled
        if not self.enabled:
            return

        if path is not None and base_path is not None:
            raise error.Error("You can pass at most one of `path` or `base_path`.")

        self.last_frame = None
        self.env = env

        required_ext = ".json" if self.ansi_mode else ".mp4"
        if path is None:
            if base_path is not None:
                # Base path given, append ext
                path = base_path + required_ext
            else:
                # Otherwise, just generate a unique filename
                with tempfile.NamedTemporaryFile(
                    suffix=required_ext, delete=False
                ) as f:
                    path = f.name
        self.path = path

        path_base, actual_ext = os.path.splitext(self.path)

        if actual_ext != required_ext:
            if self.ansi_mode:
                hint = (
                    " HINT: The environment is text-only, "
                    "therefore we're recording its text output in a structured JSON format."
                )
            else:
                hint = ""
            raise error.Error(
                f"Invalid path given: {self.path} -- must have file extension {required_ext}.{hint}"
            )
        # Touch the file in any case, so we know it's present. This corrects for platform platform differences.
        # Using ffmpeg on OS X, the file is precreated, but not on Linux.
        touch(path)

        self.frames_per_sec = env.metadata.get("render_fps", 30)
        self.output_frames_per_sec = env.metadata.get("render_fps", self.frames_per_sec)

        # backward-compatibility mode:
        self.backward_compatible_frames_per_sec = env.metadata.get(
            "video.frames_per_second", self.frames_per_sec
        )
        self.backward_compatible_output_frames_per_sec = env.metadata.get(
            "video.output_frames_per_second", self.output_frames_per_sec
        )
        if self.frames_per_sec != self.backward_compatible_frames_per_sec:
            logger.deprecation(
                '`env.metadata["video.frames_per_second"] is marked as deprecated and will be replaced '
                'with `env.metadata["render_fps"]` see https://github.com/openai/gym/pull/2654 for more details'
            )
            self.frames_per_sec = self.backward_compatible_frames_per_sec
        if self.output_frames_per_sec != self.backward_compatible_output_frames_per_sec:
            logger.deprecation(
                '`env.metadata["video.output_frames_per_second"] is marked as deprecated and will be replaced '
                'with `env.metadata["render_fps"]` see https://github.com/openai/gym/pull/2654 for more details'
            )
            self.output_frames_per_sec = self.backward_compatible_output_frames_per_sec

        self.encoder = None  # lazily start the process
        self.broken = False

        # Dump metadata
        self.metadata = metadata or {}
        self.metadata["content_type"] = (
            "video/vnd.openai.ansivid" if self.ansi_mode else "video/mp4"
        )
        self.metadata_path = f"{path_base}.meta.json"
        self.write_metadata()

        logger.info(f"Starting new video recorder writing to {self.path}")
        self.empty = True

    @property
    def functional(self):
        """Returns if the video recorder is functional, is enabled and not broken."""
        return self.enabled and not self.broken

    def capture_frame(self):
        """Render the given `env` and add the resulting frame to the video."""
        if not self.functional:
            return
        if self._closed:
            logger.warn(
                "The video recorder has been closed and no frames will be captured anymore."                )
            return
        logger.debug("Capturing video frame: path=%s", self.path)

        render_mode = "ansi" if self.ansi_mode else "rgb_array"
        frame = self.env.render(mode=render_mode)
        def make_frame(t):
            curr_frame = frame[t]
            return curr_frame
        
        clip = mpy.VideoClip(make_frame, duration = len(frame))
        clip.write_videofile(self.path)        
    
    def close(self):
        """Flush all data to disk and close any open frame encoders."""
        if not self.enabled or self._closed:
            return

        if self.encoder:
            logger.debug("Closing video encoder: path=%s", self.path)
            self.encoder.close()
            self.encoder = None
        else:
            # No frames captured. Set metadata, and remove the empty output file.
            os.remove(self.path)

            if self.metadata is None:
                self.metadata = {}
            self.metadata["empty"] = True

        # If broken, get rid of the output file, otherwise we'd leak it.
        if self.broken:
            logger.info(
                "Cleaning up paths for broken video recorder: path=%s metadata_path=%s",
                self.path,
                self.metadata_path,
            )

            # Might have crashed before even starting the output file, don't try to remove in that case.
            if os.path.exists(self.path):
                os.remove(self.path)

            if self.metadata is None:
                self.metadata = {}
            self.metadata["broken"] = True

        self.write_metadata()

        # Stop tracking this for autoclose
        self._closed = True

    def write_metadata(self):
        """Writes metadata to metadata path."""
        with open(self.metadata_path, "w") as f:
            json.dump(self.metadata, f)

    def __del__(self):
        """Closes the environment correctly when the recorder is deleted."""
        # Make sure we've closed up shop when garbage collecting
        self.close()
        