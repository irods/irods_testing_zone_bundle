#!/usr/bin/python

import abc
import glob
import itertools
import json
import os
import shutil

from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *

install_pip()
pip_install_irods_python_ci_utilities()
import irods_python_ci_utilities as ci


def do(irods_repository, irods_commitish, icommands_repository, icommands_commitish, output_directory):
    install_building_dependencies()

    irods_git_dir = ci.git_clone(irods_repository, irods_commitish)
    install_irods_externals_dependencies(irods_git_dir)
    irods_build_dir = tempfile.mkdtemp(prefix='irods_build_dir')
    irods_install_dir = tempfile.mkdtemp(prefix='irods_install_dir')
    build_irods(irods_git_dir, irods_build_dir, irods_install_dir)

    icommands_git_dir = ci.git_clone(icommands_repository, icommands_commitish)
    icommands_build_dir = tempfile.mkdtemp(prefix='icommands_build_dir')
    build_icommands(icommands_git_dir, icommands_build_dir, irods_install_dir)

    ci.install_database('postgres')
    configure_database()
    install_database_plugin_dependencies()
    configure_hostname()
    set_non_package_install_environment_variables(irods_install_dir)
    setup_irods(irods_install_dir)
    install_testing_dependencies()
    run_irods_tests(irods_install_dir)
    if output_directory:
        copy_output(irods_install_dir, output_directory)

def install_building_dependencies():
    dispatch_map = {
        'Ubuntu': install_building_dependencies_debian,
        'Centos': install_building_dependencies_redhat,
        'Centos linux': install_building_dependencies_redhat,
        'Opensuse ': install_building_dependencies_suse,
    }
    try:
        dispatch_map[ci.get_distribution()]()
    except KeyError:
        ci.raise_not_implemented_for_distribution()

def install_building_dependencies_debian():
    ci.install_os_packages(['git', 'g++', 'make', 'python-dev', 'help2man', 'unixodbc', 'libfuse-dev', 'libcurl4-gnutls-dev', 'libbz2-dev', 'zlib1g-dev', 'libpam0g-dev', 'libssl-dev', 'libxml2-dev', 'libkrb5-dev', 'unixodbc-dev', 'libjson-perl', 'python-psutil', 'fakeroot'])
    if ci.get_distribution_version_major() == '12':
        ci.install_os_packages(['python-software-properties'])
        ci.subprocess_get_output(['sudo', 'add-apt-repository', '-y', 'ppa:ubuntu-toolchain-r/test'], check_rc=True)
        ci.install_os_packages(['libstdc++6'])

def install_building_dependencies_redhat():
    base = ['git', 'python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'curl-devel', 'bzip2-devel', 'zlib-devel', 'pam-devel', 'openssl-devel', 'libxml2-devel', 'krb5-devel', 'unixODBC-devel', 'perl-JSON', 'python-psutil', 'fakeroot']
    version_specific = {
        '6': [],
        '7': ['mysql++-devel'],
    }
    ci.install_os_packages(base + version_specific[ci.get_distribution_version_major()])

def install_building_dependencies_suse():
    ci.subprocess_get_output(['sudo', 'zypper', 'addrepo', 'http://download.opensuse.org/repositories/devel:tools/openSUSE_13.2/devel:tools.repo'], check_rc=True)
    ci.subprocess_get_output(['sudo', 'zypper', '--gpg-auto-import-keys', 'refresh'], check_rc=True)
    ci.install_os_packages(['git', 'python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'libcurl-devel', 'libbz2-devel', 'libopenssl-devel', 'libxml2-devel', 'krb5-devel', 'perl-JSON', 'unixODBC-devel', 'python-psutil', 'fakeroot'])

def install_irods_externals_dependencies(irods_git_dir):
    ci.install_irods_core_dev_repository()
    with open(os.path.join(irods_git_dir, 'externals.json')) as f:
        d = json.load(f)
    ci.install_os_packages([d['cmake']] + d['others'])
    cmake_path = os.path.join('/opt/irods-externals', d['cmake'].split('irods-externals-')[1], 'bin')
    os.environ['PATH'] = ':'.join([cmake_path, os.environ['PATH']])

def build_irods(irods_git_dir, irods_build_dir, irods_install_dir):
    ci.subprocess_get_output('cmake {0} -DCMAKE_INSTALL_PREFIX={1} > cmake_irods.output'.format(irods_git_dir, irods_install_dir), cwd=irods_build_dir, shell=True, check_rc=True)
    ci.subprocess_get_output('make -j4 non-package-install-postgres > make_irods.output', cwd=irods_build_dir, shell=True, check_rc=True)

def build_icommands(icommands_git_dir, icommands_build_dir, irods_install_dir):
    IRODS_DIR = os.path.join(irods_install_dir, 'usr/lib/irods/cmake')
    ci.subprocess_get_output('cmake {0} -DCMAKE_INSTALL_PREFIX={1} -DIRODS_DIR={2} > cmake_icommands.output'.format(icommands_git_dir, irods_install_dir, IRODS_DIR), cwd=icommands_build_dir, shell=True, check_rc=True)
    ci.subprocess_get_output('make -j4 install > make_icommands.output', cwd=icommands_build_dir, shell=True, check_rc=True)

def configure_database():
    ci.subprocess_get_output(['sudo', 'su', '-', 'postgres', '-c', 'createuser -s irods'], check_rc=True)
    ci.subprocess_get_output(['sudo', 'su', '-', 'postgres', '-c', '''psql -c "alter role irods with password 'testpassword'"'''], check_rc=True)
    ci.subprocess_get_output(['sudo', 'su', '-', 'postgres', '-c', "createdb 'ICAT'"], check_rc=True)

def install_database_plugin_dependencies():
    packages = {
        'Ubuntu': ['unixodbc', 'odbc-postgresql', 'postgresql-client', 'super', 'libc6'],
    }
    ci.install_os_packages(packages[ci.get_distribution()])

def configure_hostname():
    ci.subprocess_get_output(['sudo', 'hostname', 'icat.example.org'], check_rc=True)
    ci.subprocess_get_output(['sudo', 'su', '-', '-c', 'echo -e "127.0.0.1 icat.example.org\n$(cat /etc/hosts)" > /etc/hosts'], check_rc=True)

def set_non_package_install_environment_variables(irods_install_dir):
    os.environ['LD_LIBRARY_PATH'] = os.path.join(irods_install_dir, 'usr', 'lib')
    os.environ['PATH'] = ':'.join([os.path.join(irods_install_dir, 'usr', 'bin'), os.environ['PATH']])
    os.environ['PATH'] = ':'.join([os.path.join(irods_install_dir, 'usr', 'sbin'), os.environ['PATH']])

def setup_irods(irods_install_dir):
    ci.subprocess_get_output('python scripts/setup_irods.py < packaging/localhost_setup_postgres.input', cwd=os.path.join(irods_install_dir, 'var', 'lib', 'irods'), shell=True, check_rc=True)

def install_testing_dependencies():
    ci.subprocess_get_output(['sudo', '-E', 'pip2', 'install', '--upgrade', 'unittest-xml-reporting==1.14.0'], check_rc=True)
    if not (ci.get_distribution() == 'Ubuntu' and ci.get_distribution_version_major() == '12'):
        ci.install_os_packages(['python-jsonschema'])

def run_irods_tests(irods_install_dir):
    ci.subprocess_get_output('python run_tests.py --xml_output --run_python_suite > test_output.txt 2>&1', shell=True, cwd=os.path.join(irods_install_dir, 'var', 'lib', 'irods', 'scripts'))

def copy_output(irods_install_dir, output_directory):
    ci.subprocess_get_output(['mkdir', '-p', output_directory], check_rc=True)
    ci.subprocess_get_output('cp test_output.txt {0}'.format(output_directory), cwd=os.path.join(irods_install_dir, 'var', 'lib', 'irods', 'scripts'), shell=True, check_rc=True)
    ci.subprocess_get_output('cp * {0}'.format(output_directory), cwd=os.path.join(irods_install_dir, 'var', 'lib', 'irods', 'scripts', 'test-reports'), shell=True, check_rc=True)
    ci.subprocess_get_output('cp rodsLog* {0}'.format(output_directory), cwd=os.path.join(irods_install_dir, 'var', 'lib', 'irods', 'log'), shell=True, check_rc=True)

def main():
    module = AnsibleModule(
        argument_spec = dict(
            output_directory=dict(type='str', required=False),
            irods_git_repository=dict(type='str', required=True),
            irods_git_commitish=dict(type='str', required=True),
            icommands_git_repository=dict(type='str', required=True),
            icommands_git_commitish=dict(type='str', required=True),
            debug_build=dict(type='bool', required=True),
        ),
        supports_check_mode=False,
    )

    do(module.params['irods_git_repository'], module.params['irods_git_commitish'], module.params['icommands_git_repository'], module.params['icommands_git_commitish'], module.params['output_directory'])

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    result['irods_platform_string'] = get_irods_platform_string()
    module.exit_json(**result)

main()
