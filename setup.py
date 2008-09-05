
# To build extensions you need svn version of macholib (http://svn.pythonmac.org/macholib/macholib/trunk/) In addition to the py2app package.

# bdist_mpkg (to create a osx gui installer) does not currently work on Leopard - but may at some point.


import ez_setup
ez_setup.use_setuptools()

import sys, glob
from setuptools import setup, Extension, find_packages

if sys.version < '2.4':
    print "This package requires Python version 2.4 or higher. Aborting."
    print "Visit http://www.python.org/download for a more recent version of Python."
    print "Aborting."
    sys.exit()

guiscript = 'SAP/GUI.py'

if sys.platform == 'darwin':
    # Cross-platform applications generally expect sys.argv to be used for opening files:
    extra_options = dict(setup_requires=['py2app'],
                         app=[guiscript],
                         options = dict(py2app = dict( argv_emulation=True,
                                                       iconfile='icons/app.icns'),                                       
                                        plist = dict( CFBundleName               = "SAP",
                                                      CFBundleShortVersionString = "1.0.0",     # must be in X.X.X format
                                                      CFBundleGetInfoString      = "MyAppName 1.0.0",
                                                      CFBundleExecutable         = "SAP",
                                                      CFBundleIdentifier         = "com.example.myappname",
                                                      CFBundleDocumentTypes=[dict(CFBundleTypeExtensions=['.fasta'],
                                                                                  #dict(CFBundleTypeIconFile='doc.icns'),
                                                                                  CFBundleTypeName='Fasta file',
                                                                                  CFBundleTypeRole="Viewer"), ],
                                                      #LSPrefersPPC=True,
                                                      ),
                                        )
                         )

    
elif sys.platform == 'win32':
    extra_options = dict(setup_requires=['py2exe'], app=[guiscript],)
else:
    extra_options = {}

setup(name='SAP',
      version='1.0',
      description='Statistical assignment of DNA (max 200 chars)',
      long_description='SAP does statistial assignment of unknown DNA to estabilish what taxononomic groups the DNA sample originates from. Itx uses a Baysian approach to calculate a probability distribution over all taxa represented in a sequence database. The probability of assignment to eaach taxa serves as a measure of confidence in the assignment.',
      author='Kasper Munch',
      author_email='kasmunch@bi.ku.dk',
      url='http://www.binf.ku.dk/~kasper/wiki/SAP.html',
      packages = find_packages(exclude=['ez_setup']),
      package_dir = {'SAP': 'SAP'},
      include_package_data = True,
      entry_points = { 'console_scripts': [ 'sap = SAP.ConsoleScripts:sap', ],
                       'gui_scripts': [ 'sap_gui = SAP.GUI:start_gui', ],
                       'sap.database': [ 'Native = SAP.Databases.Native', 'GenBank = SAP.Databases.GenBank' ],
                       'sap.alignment': [ 'Clustalw2 = SAP.Alignment.Clustalw2', 'MapToPreAligned = SAP.Alignment.MapToPreAligned' ],
                       'sap.sampler': [ 'Barcoder = SAP.Sampling.Barcoder', 'CNJB = SAP.Sampling.ConstrainedNJ' ],
                       },
      ext_modules=[Extension('SAP.Sampling.Barcoder._Barcoder', # Has to be prefixed with the underscore because this is the name generated by swig.
                             glob.glob('ext/barcoder/*.c[px][px]'),
                             include_dirs=['ext/barcoder']
                             ),
                   Extension('SAP.Sampling.ConstrainedNJ._cConstrainedNJlib', # Has to be prefixed with the underscore because this is the name generated by swig.
                             glob.glob('ext/constrnj/*.c[px][px]'),
                             include_dirs=['ext/constrnj']
                             ),
                   Extension('SAP.Bio.Nexus.cnexus',
                             ['SAP/Bio/Nexus/cnexus.c']
                             ),
                   ],
      **extra_options
      )


