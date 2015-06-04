#!/usr/bin/python

import abc
import json
import os
import platform
import socket
import subprocess
import sys
import time


def get_distribution_version_major():
    return get_distribution_version().split('.')[0]

def get_target_identifier():
    return get_distribution() + '_' + get_distribution_version_major()

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
        return []

    @abc.abstractmethod
    def install_packages(self, packages):
        pass

    @abc.abstractmethod
    def install_packages_from_file(self, packages):
        pass

    @property
    def irods_packages_directory(self):
        return os.path.join(self.irods_packages_root_directory, get_target_identifier())

    def install(self):
        self.install_testing_dependencies()
        self.install_resource()
        self.run_setup_script()

    def install_testing_dependencies(self):
        if self.testing_dependencies:
            self.install_packages(self.testing_dependencies)
        self.module.run_command('wget https://bootstrap.pypa.io/get-pip.py', check_rc=True)
        self.module.run_command('sudo -E python get-pip.py', check_rc=True)
        self.module.run_command('sudo -E pip2 install unittest-xml-reporting', check_rc=True)

    def install_resource(self):
        resource_package_basename = filter(lambda x:'irods-resource' in x, os.listdir(self.irods_packages_directory))[0]
        resource_package = os.path.join(self.irods_packages_directory, resource_package_basename)
        self.install_packages_from_file([resource_package])

    def run_setup_script(self):
        setup_script_inputs = ['']*13 + [self.icat_server_hostname, 'tempZone', '', 'rods']
        setup_script_string = '\n'.join(setup_script_inputs) + '\n'
        self.module.run_command('sudo /var/lib/irods/packaging/setup_irods.sh', data=setup_script_string, check_rc=True)

class RedHatStrategy(GenericStrategy):
    @property
    def testing_dependencies(self):
        return super(RedHatStrategy, self).testing_dependencies + ['python-unittest2']

    def install_packages(self, packages):
        args = ['sudo', 'yum', 'install', '-y'] + packages
        self.module.run_command(args, check_rc=True)

    def install_packages_from_file(self, packages):
        args = ['sudo', 'yum', 'localinstall', '-y', '--nogpgcheck'] + packages
        self.module.run_command(args, check_rc=True)

class DebianStrategy(GenericStrategy):
    def install_packages(self, packages):
        self.module.run_command('sudo apt-get update', check_rc=True)
        args = ['sudo', 'apt-get', 'install', '-y'] + packages
        self.module.run_command(args, check_rc=True)

    def install_packages_from_file(self, packages):
        args = ['sudo', 'dpkg', '-i'] + packages
        self.module.run_command(args) # no check_rc, missing deps return code 1
        self.module.run_command('sudo apt-get update', check_rc=True)
        self.module.run_command('sudo apt-get install -yf')

class SuseStrategy(GenericStrategy):
    def install_packages(self, packages):
        args = ['sudo', 'zypper', '--non-interactive', 'install'] + packages
        self.module.run_command(args, check_rc=True)

    def install_packages_from_file(self, packages):
        self.install_packages(packages)

class CentOSResourceInstaller(ResourceInstaller):
    platform = 'Linux'
    distribution = 'Centos'
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
main()
