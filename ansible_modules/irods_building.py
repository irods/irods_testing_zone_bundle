#!/usr/bin/python

import abc
import json
import os
import shutil


class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplemented_error()

    def build(self):
        self.unimplemented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_building module cannot be used on platform {0}'.format(msg_platform))

class Builder(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(Builder, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def build(self):
        return self.strategy.build()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.output_root_directory = module.params['output_root_directory']
        self.git_repository = module.params['git_repository']
        self.git_commitish = module.params['git_commitish']
        self.debug_build = module.params['debug_build']
        self.local_irods_git_dir = os.path.expanduser('~/irods')

    @abc.abstractproperty
    def building_dependencies(self):
        pass

    @property
    def output_directory(self):
        return os.path.join(self.output_root_directory, get_irods_platform_string())

    def build(self):
        self.install_building_dependencies()
        self.prepare_git_repository()
        self.build_irods_packages_and_copy_output()

    def install_building_dependencies(self):
        install_os_packages(self.building_dependencies)

    def prepare_git_repository(self):
        self.module.run_command('git clone --recursive {0} {1}'.format(self.git_repository, self.local_irods_git_dir), check_rc=True)
        self.module.run_command('git checkout {0}'.format(self.git_commitish), cwd=self.local_irods_git_dir, check_rc=True)
        self.module.run_command('git submodule update --init --recursive', cwd=self.local_irods_git_dir, check_rc=True)

    def build_irods_packages_and_copy_output(self):
        try:
            self.build_irods_packages()
        finally:
            shutil.copytree(os.path.join(self.local_irods_git_dir, 'build'), self.output_directory)

    def build_irods_packages(self):
        os.makedirs(os.path.join(self.local_irods_git_dir, 'build'))
        build_flags = '' if self.debug_build else '-r'
        self.module.run_command('sudo ./packaging/build.sh {0} icat postgres > ./build/build_output_icat_postgres.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('sudo ./packaging/build.sh {0} resource postgres > ./build/build_output_resource.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('sudo ./packaging/build.sh {0} icat mysql > ./build/build_output_icat_mysql.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

class RedHatStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        base = ['git', 'python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'curl-devel', 'bzip2-devel', 'zlib-devel', 'pam-devel', 'openssl-devel', 'libxml2-devel', 'krb5-devel', 'unixODBC-devel', 'perl-JSON', 'python-psutil']
        version_specific = {
            '6': [],
            '7': ['mysql++-devel'],
        }
        return base + version_specific[get_distribution_version_major()]

    def install_building_dependencies(self):
        super(RedHatStrategy, self).install_building_dependencies()
        if get_distribution_version_major() == '6':
            self.install_oracle_dependencies()

    def install_oracle_dependencies(self):
        tar_file = os.path.expanduser('~/oci.tar')
        self.module.run_command(['wget', 'http://people.renci.org/~jasonc/irods/oci.tar', '-O', tar_file], check_rc=True)
        tar_dir = os.path.expanduser('~/oci')
        os.mkdir(tar_dir)
        self.module.run_command(['tar', '-xf', 'oci.tar', '-C', tar_dir], check_rc=True)
        self.module.run_command('sudo rpm -i --nodeps ./oci/*', use_unsafe_shell=True, check_rc=True)

    def build_irods_packages(self):
        super(RedHatStrategy, self).build_irods_packages()
        if get_distribution_version_major() == '6':
            build_flags = '' if self.debug_build else '-r'
            self.module.run_command('sudo ./packaging/build.sh {0} icat oracle > ./build/build_output_icat_oracle.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

class DebianStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['git', 'g++', 'make', 'python-dev', 'help2man', 'unixodbc', 'libfuse-dev', 'libcurl4-gnutls-dev', 'libbz2-dev', 'zlib1g-dev', 'libpam0g-dev', 'libssl-dev', 'libxml2-dev', 'libkrb5-dev', 'unixodbc-dev', 'libjson-perl', 'python-psutil']

    def install_building_dependencies(self):
        super(DebianStrategy, self).install_building_dependencies()
        self.install_oracle_dependencies()

    def install_oracle_dependencies(self):
        tar_file = os.path.expanduser('~/oci.tar')
        self.module.run_command(['wget', 'http://people.renci.org/~jasonc/irods/oci.tar', '-O', tar_file], check_rc=True)
        tar_dir = os.path.expanduser('~/oci')
        os.mkdir(tar_dir)
        self.module.run_command(['tar', '-xf', 'oci.tar', '-C', tar_dir], check_rc=True)
        install_os_packages(['alien', 'libaio1'])
        self.module.run_command('sudo alien -i ./oci/*', use_unsafe_shell=True, check_rc=True)

    def build_irods_packages(self):
        super(DebianStrategy, self).build_irods_packages()
        build_flags = '' if self.debug_build else '-r'
        self.module.run_command('sudo ./packaging/build.sh {0} icat oracle > ./build/build_output_icat_oracle.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

class SuseStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['git', 'python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'libcurl-devel', 'libbz2-devel', 'libopenssl-devel', 'libxml2-devel', 'krb5-devel', 'perl-JSON', 'unixODBC-devel', 'python-psutil']

class CentOS6Builder(Builder):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = RedHatStrategy

class CentOS7Builder(Builder):
    platform = 'Linux'
    distribution = 'Centos linux'
    strategy_class = RedHatStrategy

class UbuntuBuilder(Builder):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = DebianStrategy

class OpenSuseBuilder(Builder):
    platform = 'Linux'
    distribution = 'Opensuse '
    strategy_class = SuseStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            output_root_directory=dict(type='str', required=True),
            git_repository=dict(type='str', required=True),
            git_commitish=dict(type='str', required=True),
            debug_build=dict(type='bool', required=True),
        ),
        supports_check_mode=False,
    )

    builder = Builder(module)
    builder.build()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
