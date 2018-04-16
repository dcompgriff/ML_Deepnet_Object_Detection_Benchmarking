#!/usr/bin/env python2

# Copyright (c) 2017-present, Facebook, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##############################################################################

"""Perform inference on a single image or all images with a certain extension
(e.g., .jpg) in a folder.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from collections import defaultdict
import json
import argparse
import cv2  # NOQA (Must import before importing caffe2 due to bug in cv2)
import glob
import logging
import os
import sys
import time

from caffe2.python import workspace

from core.config import assert_and_infer_cfg
from core.config import cfg
from core.config import merge_cfg_from_file
from utils.io import cache_url
from utils.timer import Timer
import core.test_engine as infer_engine
import datasets.dummy_datasets as dummy_datasets
import utils.c2 as c2_utils
import utils.logging
import utils.vis as vis_utils

c2_utils.import_detectron_ops()
# OpenCL may be enabled by default in OpenCV3; disable it because it's not
# thread safe and causes unwanted GPU memory allocations.
cv2.ocl.setUseOpenCL(False)


def parse_args():
    parser = argparse.ArgumentParser(description='End-to-end inference')
    parser.add_argument(
        '--cfg',
        dest='cfg',
        help='cfg model file (/path/to/model_config.yaml)',
        default=None,
        type=str
    )
    parser.add_argument(
        '--wts',
        dest='weights',
        help='weights model file (/path/to/model_weights.pkl)',
        default=None,
        type=str
    )
    parser.add_argument(
        '--output-dir',
        dest='output_dir',
        help='directory for visualization pdfs (default: /tmp/infer_simple)',
        default='/tmp/infer_simple',
        type=str
    )
    parser.add_argument(
        '--image-ext',
        dest='image_ext',
        help='image file name extension (default: jpg)',
        default='jpg',
        type=str
    )
    parser.add_argument(
        'im_or_folder', help='image or folder of images', default=None
    )
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    return parser.parse_args()


def main(args):

    #logger = logging.getLogger(__name__)

    outLogName = os.path.join(args.output_dir, os.path.basename(args.cfg).split(".")[0] + '.log')
    logging.basicConfig(filename=outLogName, level=logging.INFO, format= '%(levelname)s %(filename)s:%(lineno)4d: %(message)s', filemode='w')
    logger = logging.getLogger(__name__)
    
    merge_cfg_from_file(args.cfg)
    cfg.NUM_GPUS = 4
    args.weights = cache_url(args.weights, cfg.DOWNLOAD_CACHE)
    assert_and_infer_cfg(cache_urls=False)
    model = infer_engine.initialize_model_from_cfg(args.weights)
    dummy_coco_dataset = dummy_datasets.get_coco_dataset()

    if os.path.isdir(args.im_or_folder):
        im_list = glob.iglob(args.im_or_folder + '/*.' + args.image_ext)
    else:
        im_list = [args.im_or_folder]

    # Set up the array of dicts that will eventually be converted to a
    # json output file.
    imgObjectArray = []

    # For each image, get the list of bounding boxes, classes, and keypoints.
    # numFiles = len(list(enumerate(im_list)))
    for i, im_name in enumerate(im_list):
        # Create the output object.
        imgObject = {"img_name": im_name, "score": [], "bbox": [], "classes": []}

        #out_name = os.path.join(
        #    args.output_dir, '{}'.format(os.path.basename(im_name) + '.pdf')
        #)
        logger.info('Processing {}: {} -> {}'.format(str(i+1), im_name, args.cfg.split(".")[0] + '.json'))
        im = cv2.imread(im_name)
        timers = defaultdict(Timer)
        t = time.time()
        with c2_utils.NamedCudaScope(0):
            cls_boxes, cls_segms, cls_keyps = infer_engine.im_detect_all(
                model, im, None, timers=timers
            )

        # Use the utils.vis package to get the set of classes.
        boxes, segms, keyps, classes = vis_utils.convert_from_cls_format(cls_boxes, cls_segms, cls_keyps)
        imgObject["scores"] = boxes[:, 4].tolist()
        imgObject["bboxes"] = boxes[:, :3].tolist()
        imgObject["classes"] = classes
        # Add this image to the final array of objects.
        imgObjectArray.append(imgObject)
            
        #logger.info('Inference time: {:.3f}s'.format(time.time() - t))
        #for k, v in timers.items():
        #    logger.info(' | {}: {:.3f}s'.format(k, v.average_time))
    
    #import pdb; pdb.set_trace()
    outObjName = os.path.join(args.output_dir, os.path.basename(args.cfg).split(".")[0] + '.json')
    with open(outObjName, 'w') as outfile:
        json.dump(imgObjectArray, outfile)


            
'''
        vis_utils.vis_one_image(
            im[:, :, ::-1],  # BGR -> RGB for visualization
            im_name,
            args.output_dir,
            cls_boxes,
            cls_segms,
            cls_keyps,
            dataset=dummy_coco_dataset,
            box_alpha=0.3,
            show_class=True,
            thresh=0.7,
            kp_thresh=2
        )
'''


if __name__ == '__main__':
    workspace.GlobalInit(['caffe2', '--caffe2_log_level=0'])
    #utils.logging.setup_logging(__name__)
    args = parse_args()
    main(args)
