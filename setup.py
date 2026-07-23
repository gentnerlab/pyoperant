from setuptools import setup

setup(
    name='pyoperant',
    version='0.1.2',
    author='Justin Kiggins',
    author_email='justin.kiggins@gmail.com',
    maintainer='Timothy Gentner',
    maintainer_email='tgentner@ucsd.edu',
    description='hardware interface and controls for operant conditioning',
    long_description=open('docs/README.rst', 'rt').read(),
    packages=['pyoperant'],
    install_requires=['ephem', 'numpy'],
    python_requires='>=3.9',
    scripts=[
        'scripts/behave',
        # Deprecated stub (kept so `pyoperantctl` points users at rpioperantctl
        # on the MagPi server); the legacy Perl controller has been retired.
        'scripts/pyoperantctl',
        'scripts/mutate_config_file',
        'scripts/tune_servo.py',
        'scripts/test_panel.py',
        'scripts/test_ir.py',
    ],
    license='BSD',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: Unix',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Scientific/Engineering',
    ],
)
