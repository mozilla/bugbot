import os

from setuptools import setup, find_packages


root = os.path.abspath(os.path.dirname(__file__))
path = lambda *p: os.path.join(root, *p)


setup(
    name='bztools',
    version=__import__('bugzilla').__version__,
    description='Models and scripts to access the Bugzilla REST API.',
    long_description=open(path('README.rst')).read(),
    author='Jeff Balogh',
    author_email='me@jeffbalogh.org',
    url='http://github.com/LegNeato/bztools',
    license='BSD',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    # install_requires=['remoteobjects>=1.1'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    entry_points={
        'console_scripts': [
            'bzattach = scripts.attach:main',
        ],
    },
)
