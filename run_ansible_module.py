import argparse
import sys

import library


def run_ansible_module(run_name, ansible_module, ansible_arguments, sudo=False, platform_targets=None, ansible_module_directories=None, leak_vms=False):
    if platform_targets is None:
        platform_targets = [('CentOS', '6'), ('CentOS', '7'), ('Ubuntu', '12'), ('Ubuntu', '14'), ('openSUSE ', '13')]
    else:
        platform_targets = eval(platform_targets) # e.g.  platform_targets = [('CentOS', '6'), ('Ubuntu', '12'), ('Ubuntu', '14'), ('openSUSE ', '13')]

    if ansible_module_directories is None:
        ansible_module_directories = []

    vm_names, ip_addresses = library.deploy_vms_return_names_and_ips(run_name, platform_targets)
    with library.vm_manager(vm_names, leak_vms):
        run_ansible_module_on_vms(ip_addresses, ansible_module, ansible_arguments, sudo, ansible_module_directories)

def run_ansible_module_on_vms(ip_addresses, ansible_module, ansible_arguments, sudo, ansible_module_directories):
    library.run_ansible(module_name=ansible_module, complex_args=ansible_arguments,
                        host_list=ip_addresses, additional_modules_directories=ansible_module_directories, sudo=sudo)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build iRODS packages')
    parser.add_argument('--run_name', type=str, required=True)
    parser.add_argument('--ansible_module', type=str, required=True)
    parser.add_argument('--ansible_arguments', nargs='+', required=True)
    parser.add_argument('--ansible_module_directories', nargs='+', default=[])
    parser.add_argument('--platform_targets', type=str)
    parser.add_argument('--sudo', action='store_true')
    parser.add_argument('--leak_vms', action='store_true')
    args = parser.parse_args()

    if len(args.ansible_arguments) % 2 != 0:
        sys.exit('--ansible_arguments must have an even number of arguments')
    ansible_arguments = {args.ansible_arguments[i]: args.ansible_arguments[i+1] for i in range(0, len(args.ansible_arguments), 2)}

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    run_ansible_module(args.run_name, args.ansible_module, ansible_arguments, args.sudo, args.platform_targets, args.ansible_module_directories, args.leak_vms)
