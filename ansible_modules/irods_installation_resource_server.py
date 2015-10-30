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
        self.icat_server_hostname = module.params['icat_server_hostname']

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
        self.module.run_command('sudo -E pip2 install --upgrade unittest-xml-reporting', check_rc=True)

    def install_resource(self):
        resource_package_basename = filter(lambda x:'irods-resource' in x, os.listdir(self.irods_packages_directory))[0]
        resource_package = os.path.join(self.irods_packages_directory, resource_package_basename)
        install_os_packages_from_files([resource_package])

    def run_setup_script(self):
        if get_irods_version() < (4, 1):
            self.fix_403_setup_script()
            setup_script_inputs = ['']*8 + ['rods', '', self.icat_server_hostname, 'tempZone', '', 'rods']
            setup_script_string = '\n'.join(setup_script_inputs) + '\n'
        else:
            setup_script_inputs = ['']*13 + [self.icat_server_hostname, 'tempZone', '', 'rods']
            setup_script_string = '\n'.join(setup_script_inputs) + '\n'
        setup_script_input_file_initial = '/home/irodsbuild/setup_irods.input'
        setup_script_input_file_final = '/var/lib/irods/iRODS/installLogs/setup_irods.input'
        with open(setup_script_input_file_initial, 'w') as f:
            f.write(setup_script_string)
        self.module.run_command(['sudo', 'mv', setup_script_input_file_initial, setup_script_input_file_final], check_rc=True)
        output_log = '/var/lib/irods/iRODS/installLogs/setup_irods.output'
        self.module.run_command(['sudo', 'su', '-c', '/var/lib/irods/packaging/setup_irods.sh < {0} 2>&1 | tee {1}; exit $PIPESTATUS'.format(setup_script_input_file_final, output_log)], use_unsafe_shell=True, check_rc=True)

    def fix_403_setup_script(self):
        # https://github.com/irods/irods/issues/2498
        script = '/var/lib/irods/packaging/get_icat_server_password.sh'
        with open(script, 'rb') as f:
            b = f.read()
        sha256_hex_403 = '0349c2c31a52dc21f77ffe8cb4bb16f3ce3bdf1b86a14e94ba994f8a7905b137'
        h = hashlib.sha256()
        h.update(b)
        if h.hexdigest() == sha256_hex_403:
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
            icat_server_hostname=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    installer = ResourceInstaller(module)
    installer.install()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
