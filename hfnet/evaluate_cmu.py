import logging
from pathlib import Path
import argparse
from pprint import pformat
import yaml
import numpy as np
from pyquaternion import Quaternion

from hfnet.evaluation.localization import Localization, evaluate
from hfnet.evaluation.loaders import export_loader
from hfnet.settings import EXPER_PATH


configs_global = {
    'netvlad': {
        'db_name': 'globaldb_netvlad_sift.pkl',
        'experiment': 'netvlad/cmu_resize-1024',
        'predictor': export_loader,
        'has_keypoints': False,
        'has_descriptors': False,
        'pca_dim': 1024,
        'num_prior': 10,
    },
    'hfnet': {
        'db_name': 'globaldb_hf_glm-bdd_lrsteps.pkl',
        'experiment': 'hfnet-shared_weights-unc_aug-photo_glm-bdd_lrsteps/cmu_resize-1024',
        'predictor': export_loader,
        'has_keypoints': False,
        'has_descriptors': False,
        'pca_dim': 1024,
        'num_prior': 10,
    },
}

configs_local = {
    'superpoint': {
        'db_name': 'localdb_sp-nms4-ratio85.pkl',
        'experiment': 'super_point_pytorch/cmu_resize-1024',
        'predictor': export_loader,
        'has_keypoints': True,
        'has_descriptors': True,
        'binarize': False,
        'do_nms': True,
        'nms_thresh': 4,
        'num_features': 2000,
        'ratio_thresh': 0.9,
        'nms_refinement': False,
    },
    'sift': {
        'db_name': 'localdb_sift.pkl',
        'colmap_db': 'colmapdb_sift_database.db',
        'colmap_db_queries': 'colmapdb_sift_queries.db',
        'broken_paths': True,
        'root': False,
        'ratio_thresh': 0.7,
    },
    'hfnet': {
        'db_name': 'localdb_hf_glm-bdd_lrsteps.pkl',
        'experiment': 'hfnet-shared_weights-unc_aug-photo_glm-bdd_lrsteps/cmu_resize-1024',
        'predictor': export_loader,
        'has_keypoints': True,
        'has_descriptors': True,
        'do_nms': True,
        'nms_thresh': 4,
        'num_features': 2000,
        'ratio_thresh': 0.9,
    },
}

config_pose = {
    'reproj_error': 5,
    'min_inliers': 12,
}

config_cmu = {
    'name': 'cmu',
    'resize_max': 1024,
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', type=str)
    parser.add_argument('eval_name', type=str)
    parser.add_argument('--local_method', type=str, required=True)
    parser.add_argument('--global_method', type=str, required=True)
    parser.add_argument('--build_db', action='store_true')
    parser.add_argument('--slice', type=str, required=True)
    parser.add_argument('--max_iter', type=int)
    parser.add_argument('--export_poses', action='store_true')
    parser.add_argument('--cpp_backend', action='store_true')
    args = parser.parse_args()

    config = {
        'global': configs_global[args.global_method],
        'local': configs_local[args.local_method],
        'cmu': {**config_cmu, 'prefix': args.slice},
        'pose': config_pose,
        'model': args.model,
        'max_iter': args.max_iter,
        'slice': args.slice,
        'use_cpp': args.cpp_backend,
    }
    for i in ['local', 'global']:
        if 'experiment' in config[i]:
            config[i]['experiment'] += '/' + args.slice

    name = f'cmu/{args.slice}'
    logging.info(f'Evaluating {name} with configuration: \n'+pformat(config))
    loc = Localization(name, config['model'], config, build_db=args.build_db)

    query_file = f'{args.slice}.queries_with_intrinsics.txt'
    queries, query_dataset = loc.init_queries(query_file, config['cmu'])

    logging.info('Starting evaluation')
    metrics, results = evaluate(
        loc, queries, query_dataset, max_iter=args.max_iter)
    logging.info('Evaluation metrics: \n'+pformat(metrics))

    output = {'config': config, 'metrics': metrics}
    output_dir = Path(EXPER_PATH, 'eval/cmu')
    output_dir.mkdir(exist_ok=True, parents=True)
    eval_filename = f'{args.eval_name}_{args.slice}'
    eval_path = Path(output_dir, f'{eval_filename}.yaml')
    with open(eval_path, 'w') as f:
        yaml.dump(output, f, default_flow_style=False)

    if args.export_poses:
        poses_path = Path(output_dir, f'{eval_filename}_poses.txt')
        with open(poses_path, 'w') as f:
            for query, result in zip(queries, results):
                query_T_w = np.linalg.inv(result.T)
                qvec_nvm = list(Quaternion(matrix=query_T_w))
                pos_nvm = query_T_w[:3, 3].tolist()
                name = '/'.join(query.name.split('/')[-2:])
                line = name + ' ' + ' '.join(map(str, qvec_nvm+pos_nvm))
                f.write(line+'\n')
