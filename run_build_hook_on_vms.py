import argparse

import library


def run_build_hook_on_vms(build_name, git_repository, git_commitish, platform_targets, passthrough_arguments):
    platform_targets = eval(platform_targets) # e.g.  platform_targets = [('CentOS', '6'), ('Ubuntu', '12'), ('Ubuntu', '14'), ('openSUSE ', '13')]
    vm_names, ip_addresses = library.deploy_vms_return_names_and_ips(build_name, platform_targets)
    with library.vm_manager(vm_names, leak_vms=False):
        build_plugin_on_vms(ip_addresses, git_repository, git_commitish, passthrough_arguments)

def build_plugin_on_vms(ip_addresses, git_repository, git_commitish, passthrough_arguments):
    complex_args = {
        'git_repository': git_repository,
        'git_commitish': git_commitish,
        'passthrough_arguments': passthrough_arguments,
    }

    library.run_ansible(module_name='irods_run_build_hook', complex_args=complex_args, host_list=ip_addresses)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build plugin packages')
    parser.add_argument('--build_name', type=str, required=True)
    parser.add_argument('--git_repository', type=str, required=True)
    parser.add_argument('--git_commitish', type=str, required=True)
    parser.add_argument('--platform_targets', type=str, required=True)
    parser.add_argument('--passthrough_arguments', default=[], nargs=argparse.REMAINDER)
    args = parser.parse_args()

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    run_build_hook_on_vms(args.build_name, args.git_repository, args.git_commitish, args.platform_targets, args.passthrough_arguments)
