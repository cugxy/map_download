# -*- coding: utf-8 -*-
#  coding=utf-8
import json
import os
import math
import logging
import requests
import time
import random

from map_download.cmd.BaseDownloader import DownloadEngine, BaseDownloaderThread, latlng2tile_google, BoundBox


class GoogleDownloaderThread(BaseDownloaderThread):
    URL = "http://mt{s}.google.cn/vt?lyrs=s&hl=en-US&gl=US&x={x}&y={y}&z={z}"

    def __init__(self, root_dir, bbox, task_q, logger=None, write_db=False):
        super(GoogleDownloaderThread, self).__init__(root_dir, bbox, task_q, logger, write_db=write_db,
                                                     db_file_name='Google.db')
        self._init_metadata(
            bounds='%f,%f,%f,%f' % (self.bbox.min_lng, self.bbox.min_lat, self.bbox.max_lng, self.bbox.max_lat))

    def get_url(self, x, y, z):
        s = random.randint(1, 3)
        return self.URL.format(s=s, x=x, y=y, z=z)

    def _download(self, x, y, z):
        file_path = '%s/%s/%i/%i/%i.%s' % (self.root_dir, 'Google', z, x, y, 'jpg')
        if os.path.exists(file_path):
            self._data2DB(x, y, z, file_path)
            return 0
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        resp = None
        requre_count = 0
        while True:
            if requre_count > 4: break
            try:
                _url = self.get_url(x, y, z)
                resp = requests.get(_url, stream=True, timeout=2)
                break
            except Exception as e:
                resp = None
                time.sleep(3)
            requre_count += 1
        if resp is None:
            return -1
        if resp.status_code != 200:
            return -1
        try:
            with open(file_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            return -1
        self._data2DB(x, y, z, file_path)
        return 1


class GoogleDownloadEngine(DownloadEngine):
    root_dir = ''
    URL = "http://mt{s}.google.cn/vt?lyrs=s&hl=en-US&gl=US&x={x}&y={y}&z={z}"

    def __init__(self, root_dir, bbox, thread_num, logger=None, write_db=False):
        super(GoogleDownloadEngine, self).__init__(bbox, thread_num, logger, write_db=write_db)
        self.root_dir = root_dir

    def bbox2xyz(self, bbox, z):
        min_x, min_y = latlng2tile_google(bbox.max_lat, bbox.min_lng, z)
        max_x, max_y = latlng2tile_google(bbox.min_lat, bbox.max_lng, z)
        return math.floor(min_x), math.floor(min_y), math.ceil(max_x), math.ceil(max_y)

    def generate_metadata(self):
        try:
            bounds = '%d %d %d %d' % (self.bbox.min_lng, self.bbox.min_lat, self.bbox.max_lng, self.bbox.max_lat)
            metadatas = {'attribution': self.URL,
                         'bounds': bounds,
                         'description': 'GoogleDowmloader',
                         'format': 'jpg',
                         'name': 'Google',
                         'type': 'baselayer',
                         'version': 1.2}
            _dir = os.path.join(self.root_dir, 'Google')
            os.makedirs(_dir, exist_ok=True)
            metadatas_path = os.path.join(_dir, 'metadata.json')
            with open(metadatas_path, 'w') as f:
                json.dump(metadatas, f)
        except Exception as e:
            if self.logger is not None:
                self.logger.error(e)

    def run(self):
        try:
            self.generate_metadata()
            count = 0
            bboxs = self.cut_bbox()
            for bbox in bboxs:
                _count = self.get_task_count(bbox)
                count += _count
            self.division_done_signal.emit(count)
            for bbox in bboxs:
                while True:
                    if not self.running:
                        time.sleep(0.01)
                    else:
                        break
                task_q = self.get_task_queue(bbox)
                self.threads = []
                for i in range(self.thread_num):
                    thread = GoogleDownloaderThread(self.root_dir, self.bbox, task_q, self.logger,
                                                    write_db=self.write_db)
                    thread.sub_progressBar_updated_signal.connect(self.sub_update_progressBar)
                    self.threads.append(thread)
                for thread in self.threads:
                    thread.start()
                for thread in self.threads:
                    thread.wait()
                for t in self.threads:
                    t.stop()
                    t.quit()
                self.threads = []
            self.download_done_signal.emit()
        except Exception as e:
            if self.logger is not None:
                self.logger.error(e)


if __name__ == '__main__':
    logger = logging.getLogger('down')
    try:
        root = r'D:\temp'
        formatter = logging.Formatter('%(levelname)s-%(message)s')
        hdlr = logging.StreamHandler()
        log_file = os.path.join(root, 'down.log')
        file_hdlr = logging.FileHandler(log_file)
        file_hdlr.setFormatter(formatter)
        logger.addHandler(file_hdlr)
        logger.addHandler(hdlr)
        logger.setLevel(logging.INFO)
        min_lng = -180.0
        max_lng = 180.0
        min_lat = -85.0
        max_lat = 85.0
        start_zoom = 0
        end_zoom = 10
        bbox = BoundBox(max_lat, max_lng, min_lat, min_lng, start_zoom, end_zoom)
        d = GoogleDownloadEngine(root, bbox, 1, logger)
        d.start()
        time.sleep(10000)
        logger.error('main thread out')
    except Exception as e:
        logger.error(e)
