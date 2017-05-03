import argparse
import json
import os
import sys

import deploy
import destroy
import library


def list_to_dict(l):
    return {l[i]: l[i+1] for i in range(0, len(l), 2)}

def checkout_git_repo_and_run_python_script_on_icat(deployed_zone_bundle, git_repository, git_commitish, python_script, passthrough_arguments):
    complex_args = {
        'git_repository': git_repository,
        'git_commitish': git_commitish,
        'python_script': python_script,
        'passthrough_arguments': passthrough_arguments,
    }
    return library.run_ansible(module_name='irods_clone_git_repo_and_run_python_script', complex_args=complex_args, host_list=[deployed_zone_bundle['zones'][0]['icat_server']['deployment_information']['ip_address']])

def main():
    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    parser = argparse.ArgumentParser(description='Run irods_consortium_continuous_integration_build_hook.py on icat')
    parser.add_argument('--deployment_name', type=str, required=True)
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--version_to_packages_map', type=str, nargs='+', required=True)
    parser.add_argument('--install_dev_package', type=library.make_argparse_true_or_false('--install_dev_package'), required=True)
    parser.add_argument('--git_repository', type=str, required=True)
    parser.add_argument('--git_commitish', type=str, required=True)
    parser.add_argument('--python_script', type=str, required=True)
    parser.add_argument('--leak_vms', type=library.make_argparse_true_or_false('--leak_vms'), required=True)
    parser.add_argument('--passthrough_arguments', default=[], nargs=argparse.REMAINDER)
    args = parser.parse_args()

    version_to_packages_map = list_to_dict(args.version_to_packages_map)

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    deployed_zone_bundle = deploy.deploy(zone_bundle, args.deployment_name, version_to_packages_map, install_dev_package=args.install_dev_package)
    with destroy.deployed_zone_bundle_manager(deployed_zone_bundle, on_exception=not args.leak_vms, on_regular_exit=not args.leak_vms):
        ansible_result = checkout_git_repo_and_run_python_script_on_icat(deployed_zone_bundle, args.git_repository, args.git_commitish, args.python_script, args.passthrough_arguments)

    if library.ansible_run_failed(ansible_result):
        sys.exit(1)

if __name__ == '__main__':
    main()
