import logging
import os
import traceback
from pathlib import Path
from typing import List, Union

import cv2
import numpy as np
import pandas as pd

from src.cameras.capture.dataclasses.frame_payload import FramePayload
from src.cameras.persistence.video_writer.save_options_dataclass import SaveOptions
from src.config.data_paths import freemocap_data_path
from src.config.home_dir import get_session_folder_path, get_synchronized_videos_folder_path, get_calibration_videos_folder_path, \
    get_mediapipe_annotated_videos_folder_path
from rich.progress import Progress

logger = logging.getLogger(__name__)


class VideoRecorder:
    def __init__(self,
                 video_name: str,
                 image_width: int,
                 image_height: int,
                 session_id: str,
                 fourcc: str = "MP4V",
                 calibration_video_bool: bool = False,
                 mediapipe_annotated_video_bool: bool = False,
                 ):
        self._video_name = video_name
        self._image_width = image_width
        self._image_height = image_height
        self._fourcc = fourcc
        self._frame_payload_list: List[FramePayload] = []
        self._timestamps_npy = np.empty(0)
        self._cv2_video_writer = None

        # get yr paths straight
        self._session_id = session_id
        session_path = Path(get_session_folder_path(self._session_id))

        if mediapipe_annotated_video_bool:
            self._video_folder_path = Path(get_mediapipe_annotated_videos_folder_path(self._session_id))
        elif calibration_video_bool:
            self._video_folder_path = Path(get_calibration_videos_folder_path(self._session_id))
        else:
            self._video_folder_path = Path(get_synchronized_videos_folder_path(self._session_id))

        self._video_folder_path.mkdir(parents=True, exist_ok=True)
        video_file_name = self._video_name + '.mp4'
        self._path_to_save_video_file = self._video_folder_path / video_file_name

    @property
    def video_name(self):
        return self._video_name

    @property
    def video_folder_path(self):
        return self._video_folder_path

    @property
    def path_to_save_video_file(self):
        return self._path_to_save_video_file

    @property
    def frame_count(self):
        return len(self._frame_payload_list)

    @property
    def median_framerate(self):
        if self.frame_count == 0:
            logger.error(f"No Frames to save for {self.path_to_save_video_file}")
            raise Exception
        else:
            self._gather_timestamps()
            self._median_framerate = (np.nanmedian(np.diff(self._timestamps_npy / 1e9))) ** -1

        return self._median_framerate

    def save_frame_payload_to_video_file(self, frame_payload: FramePayload):
        if self._cv2_video_writer is None:
            self._initialize_video_writer()

        self._cv2_video_writer.write(frame_payload.image)

    def close(self):
        self._cv2_video_writer.release()

    def append_frame_payload_to_list(self, frame_payload: FramePayload):
        self._frame_payload_list.append(frame_payload)

    def save_frame_payload_list_to_disk(self):
        if len(self._frame_payload_list) == 0:
            logging.error(f"No frames to save for camera: {self._video_name}")
            return

        self._gather_timestamps()
        self._initialize_video_writer()
        self._write_frame_list_to_video_file()
        self._save_timestamps()

    def save_image_list_to_disk(self,
                                image_list: List[np.ndarray],
                                frame_rate: Union[int, float] = None):
        if len(image_list) == 0:
            logging.error(f"No frames to save for : {self._video_name}")
            return

        self._initialize_video_writer(frames_per_second=frame_rate)
        self._write_image_list_to_video_file(image_list)

    def _initialize_video_writer(self, frames_per_second: Union[int, float] = None):

        if frames_per_second is None:
            frames_per_second = self.median_framerate
        else:
            frames_per_second = frames_per_second

        self._cv2_video_writer = cv2.VideoWriter(
            str(self.path_to_save_video_file),
            cv2.VideoWriter_fourcc(*self._fourcc),
            frames_per_second,
            (int(self._image_width), int(self._image_height)))

    def _write_frame_list_to_video_file(self):
        try:
            for frame in self._frame_payload_list:
                self._cv2_video_writer.write(frame.image)

        except Exception as e:
            logger.debug("Failed during save in video writer")
            traceback.print_exc()
            raise e
        finally:
            logger.info(f"Saved video to path: {self.path_to_save_video_file}")
            self._cv2_video_writer.release()

    def _write_image_list_to_video_file(self, image_list:List[np.ndarray]):
        try:
            for image in image_list:
                self._cv2_video_writer.write(image)


        except Exception as e:
            logger.error(f"Failed during save in video writer: {self.path_to_save_video_file}")
            traceback.print_exc()
            raise e
        finally:
            logger.info(f"Saved video to path: {self.path_to_save_video_file}")
            self._cv2_video_writer.release()

    def _gather_timestamps(self):
        try:
            for frame in self._frame_payload_list:
                self._timestamps_npy = np.append(self._timestamps_npy, frame.timestamp)
        except:
            logger.error("Error gathering timestamps")

    def _save_timestamps(self):
        timestamp_file_name_npy = self._video_name + "_timestamps_binary.npy"
        timestamp_npy_full_save_path = self._video_folder_path / timestamp_file_name_npy
        np.save(str(timestamp_npy_full_save_path), self._timestamps_npy)
        logger.info(f"Saved timestamps to path: {timestamp_file_name_npy}")

        timestamp_file_name_csv = self._video_name + "_timestamps_human_readable.csv"
        timestamp_csv_full_save_path = self._video_folder_path / timestamp_file_name_csv
        timestamp_dataframe = pd.DataFrame(self._timestamps_npy)
        timestamp_dataframe.to_csv(str(timestamp_csv_full_save_path))
        logger.info(f"Saved timestamps to path: {timestamp_file_name_csv}")
