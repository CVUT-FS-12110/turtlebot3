from glob import glob

from setuptools import find_packages, setup

package_name = 'auto_mapper'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Jaroslav Bušek',
    maintainer_email='jaroslav.busek@gmail.com',
    description='Autonomous frontier exploration that builds a map with slam_toolbox and Nav2.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'explorer = auto_mapper.explorer_node:main',
        ],
    },
)
