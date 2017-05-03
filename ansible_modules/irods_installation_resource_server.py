#!/usr/bin/python

import abc
import json
import hashlib
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time


class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplmented_error()

    def install(self):
        self.unimplmented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_installation_resource_server module cannot be used on platform {0}'.format(msg_platform))

class ResourceInstaller(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(ResourceInstaller, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def install(self):
        return self.strategy.install()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.irods_packages_root_directory = module.params['irods_packages_root_directory']
        self.resource_server = module.params['resource_server']
        self.install_dev_package = module.params['install_dev_package']

    @property
    def testing_dependencies(self):
        return ['git']

    @property
    def irods_packages_directory(self):
        return os.path.join(self.irods_packages_root_directory, get_irods_platform_string())

    def install(self):
        self.install_resource()
        self.run_setup_script()
        self.install_testing_dependencies()

    def install_testing_dependencies(self):
        if self.testing_dependencies:
            install_os_packages(self.testing_dependencies)
        self.module.run_command('wget https://bootstrap.pypa.io/get-pip.py', check_rc=True)
        self.module.run_command('sudo -E python get-pip.py', check_rc=True)
        self.module.run_command(['sudo', '-E', 'pip2', 'install', '--upgrade', 'unittest-xml-reporting==1.14.0'], check_rc=True)

    def install_resource(self):
        install_irods_repository()
        resource_package_basename = filter(lambda x:'irods-resource' in x or 'irods-server' in x, os.listdir(self.irods_packages_directory))[0]
        if 'irods-resource' in resource_package_basename:
            resource_package = os.path.join(self.irods_packages_directory, resource_package_basename)
            install_os_packages_from_files([resource_package])
        elif 'irods-server' in resource_package_basename:
            server_package = os.path.join(self.irods_packages_directory, resource_package_basename)
            runtime_package = server_package.replace('irods-server', 'irods-runtime')
            icommands_package = server_package.replace('irods-server', 'irods-icommands')
            install_os_packages_from_files([runtime_package, icommands_package, server_package])
        else:
            raise RuntimeError('unhandled package name')

        if self.install_dev_package:
            dev_package_basename = filter(lambda x:'irods-dev' in x, os.listdir(self.irods_packages_directory))[0]
            dev_package = os.path.join(self.irods_packages_directory, dev_package_basename)
            install_os_packages_from_files([dev_package])

    def run_setup_script(self):
        if os.path.exists('/var/lib/irods/scripts/setup_irods.py'):
            setup_input_template = '''\
{service_account_name}
{service_account_group}
2
{zone_name}
{icat_host}
{zone_port}
{server_port_range_start}
{server_port_range_end}
{control_plane_port}

{irods_admin_account_name}
yes
{zone_key}
{negotiation_key}
{control_plane_key}
{irods_admin_account_password}
{vault_directory}
'''
        elif get_irods_version() < (4, 1):
            self.fix_403_setup_script()
            setup_input_template = '''\
{service_account_name}
{service_account_group}
{zone_port}
{server_port_range_start}
{server_port_range_end}
{vault_directory}
{zone_key}
{negotiation_key}
{irods_admin_account_name}

{icat_host}
{zone_name}

{irods_admin_account_password}

'''
        else:
            setup_input_template = '''\
{service_account_name}
{service_account_group}
{zone_port}
{server_port_range_start}
{server_port_range_end}
{vault_directory}
{zone_key}
{negotiation_key}
{control_plane_port}
{control_plane_key}
{schema_validation_base_uri}
{irods_admin_account_name}

{icat_host}
{zone_name}

{irods_admin_account_password}

'''

        setup_input_values = {
            'service_account_name': '',
            'service_account_group': '',
            'zone_name': self.resource_server['server_config']['zone_name'],
            'zone_port': self.resource_server['server_config']['zone_port'],
            'server_port_range_start': self.resource_server['server_config']['server_port_range_start'],
            'server_port_range_end': self.resource_server['server_config']['server_port_range_end'],
            'vault_directory': '',
            'zone_key': self.resource_server['server_config']['zone_key'],
            'negotiation_key': self.resource_server['server_config']['negotiation_key'],
            'control_plane_port': self.resource_server['server_config']['server_control_plane_port'],
            'control_plane_key': self.resource_server['server_config']['server_control_plane_key'],
            'schema_validation_base_uri': self.resource_server['server_config']['schema_validation_base_uri'],
            'irods_admin_account_name':  self.resource_server['server_config']['zone_user'],
            'irods_admin_account_password': 'rods',
            'icat_host': self.resource_server['server_config']['icat_host']
        }

        setup_input = setup_input_template.format(**setup_input_values)

        if get_irods_version()[0:2] < (4, 2):
            output_log = '/var/lib/irods/iRODS/installLogs/setup_irods.output'
        else:
            output_log = '/var/lib/irods/log/setup_irods.output'

        def get_setup_script_location():
            if os.path.exists('/var/lib/irods/packaging/setup_irods.sh'):
                return '/var/lib/irods/packaging/setup_irods.sh'
            return 'python /var/lib/irods/scripts/setup_irods.py'
        self.module.run_command(['sudo', 'su', '-c', '{0} 2>&1 | tee {1}; exit $PIPESTATUS'.format(get_setup_script_location(), output_log)], data=setup_input, use_unsafe_shell=True, check_rc=True)

    def fix_403_setup_script(self):
        # https://github.com/irods/irods/issues/2498
        script = '/var/lib/irods/packaging/get_icat_server_password.sh'
        sha256_hex_403 = '0349c2c31a52dc21f77ffe8cb4bb16f3ce3bdf1b86a14e94ba994f8a7905b137'
        if self.module.sha256(script) == sha256_hex_403:
            self.module.run_command('sudo chmod o+w {0}'.format(script), check_rc=True)
            contents = '''\
#!/bin/bash -e

# get admin password, without showing on screen
read -s IRODS_ADMIN_PASSWORD
echo -n $IRODS_ADMIN_PASSWORD
'''
            with open(script, 'w') as f:
                f.write(contents)

class RedHatStrategy(GenericStrategy):
    @property
    def testing_dependencies(self):
        return super(RedHatStrategy, self).testing_dependencies + ['python-unittest2']

class DebianStrategy(GenericStrategy):
    pass

class SuseStrategy(GenericStrategy):
    pass

class CentOS6ResourceInstaller(ResourceInstaller):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = RedHatStrategy

class CentOS7ResourceInstaller(ResourceInstaller):
    platform = 'Linux'
    distribution = 'Centos linux'
    strategy_class = RedHatStrategy

class UbuntuResourceInstaller(ResourceInstaller):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = DebianStrategy

class OpenSUSEInstaller(ResourceInstaller):
    platform = 'Linux'
    distribution = 'Opensuse '
    strategy_class = SuseStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            irods_packages_root_directory=dict(type='str', required=True),
            resource_server=dict(type='dict', required=True),
            install_dev_package=dict(type='bool', required=True),
        ),
        supports_check_mode=False,
    )

    installer = ResourceInstaller(module)
    installer.install()

    result = {
        'changed': True,
        'complex_args': module.params,
        'irods_version': get_irods_version(),
    }

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
