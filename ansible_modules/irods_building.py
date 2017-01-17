#!/usr/bin/python

import abc
import glob
import itertools
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
        self.local_irods_build_dir = os.path.expanduser('~/build-irods')
        self.git_repository_icommands = module.params['git_repository_icommands']
        self.git_commitish_icommands = module.params['git_commitish_icommands']

    @abc.abstractproperty
    def building_dependencies(self):
        pass

    @property
    def output_directory(self):
        return os.path.join(self.output_root_directory, get_irods_platform_string())

    def build(self):
        self.install_building_dependencies()
        git_clone(self.git_repository, self.git_commitish, self.local_irods_git_dir)
        self.build_irods_packages()

    def install_building_dependencies(self):
        install_os_packages(self.building_dependencies)

    def build_irods_packages(self):
        if os.path.exists(os.path.join(self.local_irods_git_dir, 'CMakeLists.txt')):
            self.build_irods_packages_and_copy_output_cmake()
        else:
            self.build_irods_packages_and_copy_output_buildsh()

    def build_irods_packages_and_copy_output_cmake(self):
        try:
            os.makedirs(self.output_directory)
            self.build_irods_packages_cmake()
        finally:
            for f in itertools.chain(glob.glob(os.path.join(self.local_irods_build_dir, '*.{0}'.format(get_package_suffix()))),
                                     glob.glob(os.path.join(self.local_irods_build_dir, '*.output'))):
                shutil.copy2(f, self.output_directory)

    def build_irods_packages_cmake(self):
        self.install_cmake_externals()
        os.mkdir(self.local_irods_build_dir)
        self.module.run_command('cmake {0} > cmake_irods.output'.format(self.local_irods_git_dir), cwd=self.local_irods_build_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('make -j4 > {0}'.format('make_irods.output'), cwd=self.local_irods_build_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('fakeroot make package >> {0}'.format('make_irods.output'), cwd=self.local_irods_build_dir, use_unsafe_shell=True, check_rc=True)
        self.build_icommands_cmake()

    def build_icommands_cmake(self):
        install_os_packages_from_files(itertools.chain(glob.glob(os.path.join(self.local_irods_build_dir, 'irods-dev*.{0}'.format(get_package_suffix()))),
                                                       glob.glob(os.path.join(self.local_irods_build_dir, 'irods-runtime*.{0}'.format(get_package_suffix())))))
        icommands_git_dir = '/home/irodsbuild/irods_client_icommands'
        git_clone(self.git_repository_icommands, self.git_commitish_icommands, icommands_git_dir)
        icommands_build_dir = '/home/irodsbuild/icommands_build'
        os.mkdir(icommands_build_dir)
        self.module.run_command('cmake {0} > cmake_icommands.output'.format(icommands_git_dir), cwd=icommands_build_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('make -j4 > {0}'.format('make_icommands.output'), cwd=icommands_build_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('fakeroot make package >> {0}'.format('make_icommands.output'), cwd=icommands_build_dir, use_unsafe_shell=True, check_rc=True)
        for f in itertools.chain(glob.glob(os.path.join(icommands_build_dir, '*.{0}'.format(get_package_suffix()))),
                                 glob.glob(os.path.join(icommands_build_dir, '*.output'))):
            shutil.copy2(f, self.output_directory)

    def install_cmake_externals(self):
        install_irods_repository()
        with open(os.path.join(self.local_irods_git_dir, 'externals.json')) as f:
            d = json.load(f)
        install_os_packages([d['cmake']] + d['others'])
        cmake_path = os.path.join('/opt/irods-externals', d['cmake'].split('irods-externals-')[1], 'bin')
        os.environ['PATH'] = ':'.join([cmake_path, os.environ['PATH']])

    def build_irods_packages_and_copy_output_buildsh(self):
        try:
            self.build_irods_packages_buildsh()
        finally:
            shutil.copytree(os.path.join(self.local_irods_git_dir, 'build'), self.output_directory)

    def build_irods_packages_buildsh(self):
        os.makedirs(os.path.join(self.local_irods_git_dir, 'build'))
        build_flags = '' if self.debug_build else '-r'
        self.module.run_command('sudo ./packaging/build.sh {0} icat postgres > ./build/build_output_icat_postgres.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('sudo ./packaging/build.sh {0} resource postgres > ./build/build_output_resource.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('sudo ./packaging/build.sh {0} icat mysql > ./build/build_output_icat_mysql.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

class RedHatStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        base = ['git', 'python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'curl-devel', 'bzip2-devel', 'zlib-devel', 'pam-devel', 'openssl-devel', 'libxml2-devel', 'krb5-devel', 'unixODBC-devel', 'perl-JSON', 'python-psutil', 'fakeroot']
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

    def build_irods_packages_buildsh(self):
        super(RedHatStrategy, self).build_irods_packages_buildsh()
        if get_distribution_version_major() == '6':
            build_flags = '' if self.debug_build else '-r'
            self.module.run_command('sudo ./packaging/build.sh {0} icat oracle > ./build/build_output_icat_oracle.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

class DebianStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['git', 'g++', 'make', 'python-dev', 'help2man', 'unixodbc', 'libfuse-dev', 'libcurl4-gnutls-dev', 'libbz2-dev', 'zlib1g-dev', 'libpam0g-dev', 'libssl-dev', 'libxml2-dev', 'libkrb5-dev', 'unixodbc-dev', 'libjson-perl', 'python-psutil', 'fakeroot']

    def install_building_dependencies(self):
        super(DebianStrategy, self).install_building_dependencies()
        if get_distribution_version_major() == '12':
            install_os_packages(['python-software-properties'])
            self.module.run_command(['sudo', 'add-apt-repository', '-y', 'ppa:ubuntu-toolchain-r/test'], check_rc=True)
            install_os_packages(['libstdc++6'])
        self.install_oracle_dependencies()

    def install_oracle_dependencies(self):
        tar_file = os.path.expanduser('~/oci.tar')
        self.module.run_command(['wget', 'http://people.renci.org/~jasonc/irods/oci.tar', '-O', tar_file], check_rc=True)
        tar_dir = os.path.expanduser('~/oci')
        os.mkdir(tar_dir)
        self.module.run_command(['tar', '-xf', 'oci.tar', '-C', tar_dir], check_rc=True)
        install_os_packages(['alien', 'libaio1'])
        self.module.run_command('sudo alien -i ./oci/*', use_unsafe_shell=True, check_rc=True)

    def build_irods_packages_buildsh(self):
        super(DebianStrategy, self).build_irods_packages_buildsh()
        build_flags = '' if self.debug_build else '-r'
        self.module.run_command('sudo ./packaging/build.sh {0} icat oracle > ./build/build_output_icat_oracle.log 2>&1'.format(build_flags), cwd=self.local_irods_git_dir, use_unsafe_shell=True, check_rc=True)

class SuseStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['git', 'python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'libcurl-devel', 'libbz2-devel', 'libopenssl-devel', 'libxml2-devel', 'krb5-devel', 'perl-JSON', 'unixODBC-devel', 'python-psutil', 'fakeroot']

    def install_building_dependencies(self):
        self.module.run_command(['sudo', 'zypper', 'addrepo', 'http://download.opensuse.org/repositories/devel:tools/openSUSE_13.2/devel:tools.repo'], check_rc=True)
        self.module.run_command(['sudo', 'zypper', '--gpg-auto-import-keys', 'refresh'], check_rc=True)
        super(SuseStrategy, self).install_building_dependencies()

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
            git_repository_icommands=dict(type='str', required=True),
            git_commitish_icommands=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    builder = Builder(module)
    builder.build()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    result['irods_platform_string'] = get_irods_platform_string()
    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
