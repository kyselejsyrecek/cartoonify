#!/bin/bash

# The cartoonify project requires Python 2.7 due to unsupported wheels in later versions.
PYTHON_VERSION=2.7.18
export MAKEFLAGS="-j12"
export CC="gcc -m64"

sudo apt install build-essential

# Get Python.
if [ ! -f Python-$PYTHON_VERSION.tar.xz ]; then
    wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tar.xz
fi
tar xf Python-$PYTHON_VERSION.tar.xz
cd Python-$PYTHON_VERSION

# Patch Python 2.7 to work with OpenSSL 3.x.
patch -p1 << EOF
# Ported from Python 3.8.
bpo-43794: OpenSSL 3.0.0: set OP_IGNORE_UNEXPECTED_EOF by default (GH-25309)

Signed-off-by: Christian Heimes <christian@python.org>
(cherry picked from commit 6f37ebc)

Co-authored-by: Christian Heimes <christian@python.org>

diff -uNr Python-2.7.18/Lib/test/test_ssl.py Python-2.7.18.modified/Lib/test/test_ssl.py
--- Python-2.7.18/Lib/test/test_ssl.py	2020-04-19 23:13:39.000000000 +0200
+++ Python-2.7.18.modified/Lib/test/test_ssl.py	2024-02-25 10:20:18.371428722 +0100
@@ -84,6 +84,7 @@
 OP_SINGLE_ECDH_USE = getattr(ssl, "OP_SINGLE_ECDH_USE", 0)
 OP_CIPHER_SERVER_PREFERENCE = getattr(ssl, "OP_CIPHER_SERVER_PREFERENCE", 0)
 OP_ENABLE_MIDDLEBOX_COMPAT = getattr(ssl, "OP_ENABLE_MIDDLEBOX_COMPAT", 0)
+OP_IGNORE_UNEXPECTED_EOF = getattr(ssl, "OP_IGNORE_UNEXPECTED_EOF", 0)
 
 
 def handle_error(prefix):
@@ -839,7 +840,8 @@
         # SSLContext also enables these by default
         default |= (OP_NO_COMPRESSION | OP_CIPHER_SERVER_PREFERENCE |
                     OP_SINGLE_DH_USE | OP_SINGLE_ECDH_USE |
-                    OP_ENABLE_MIDDLEBOX_COMPAT)
+                    OP_ENABLE_MIDDLEBOX_COMPAT |
+                    OP_IGNORE_UNEXPECTED_EOF)
         self.assertEqual(default, ctx.options)
         ctx.options |= ssl.OP_NO_TLSv1
         self.assertEqual(default | ssl.OP_NO_TLSv1, ctx.options)
diff -uNr Python-2.7.18/Modules/_ssl.c Python-2.7.18.modified/Modules/_ssl.c
--- Python-2.7.18/Modules/_ssl.c	2020-04-19 23:13:39.000000000 +0200
+++ Python-2.7.18.modified/Modules/_ssl.c	2024-02-25 10:20:19.170425044 +0100
@@ -2260,6 +2260,10 @@
 #ifdef SSL_OP_SINGLE_ECDH_USE
     options |= SSL_OP_SINGLE_ECDH_USE;
 #endif
+#ifdef SSL_OP_IGNORE_UNEXPECTED_EOF
+    /* Make OpenSSL 3.0.0 behave like 1.1.1 */
+    options |= SSL_OP_IGNORE_UNEXPECTED_EOF;
+#endif
     SSL_CTX_set_options(self->ctx, options);
 
     /* A bare minimum cipher list without completly broken cipher suites.
@@ -4415,6 +4419,10 @@
     PyModule_AddIntConstant(m, "OP_ENABLE_MIDDLEBOX_COMPAT",
                             SSL_OP_ENABLE_MIDDLEBOX_COMPAT);
 #endif
+#ifdef SSL_OP_IGNORE_UNEXPECTED_EOF
+    PyModule_AddIntConstant(m, "OP_IGNORE_UNEXPECTED_EOF",
+                            SSL_OP_IGNORE_UNEXPECTED_EOF);
+#endif
 
 #if HAVE_SNI
     r = Py_True;
EOF

# Add MAKEFLAGS support for parallel compilation.
patch -p1 << EOF
diff -uNr Python-2.7.18/Makefile.pre.in Python-2.7.18.modified/Makefile.pre.in
--- Python-2.7.18/Makefile.pre.in	2024-02-25 11:01:05.122486094 +0100
+++ Python-2.7.18.modified/Makefile.pre.in	2024-02-25 11:04:04.741968518 +0100
@@ -68,6 +68,7 @@
 MKDIR_P=	@MKDIR_P@
 
 MAKESETUP=      $(srcdir)/Modules/makesetup
+MAKE=           $(MAKE) ${MAKEFLAGS}
 
 # Compiler options
 OPT=		@OPT@
EOF

# Compile Python 2.7
# Option "--enable-unicode=ucs4" is required by TensorFlow 1.4.0.
./configure --enable-optimizations --enable-unicode=ucs4
sudo make altinstall
cd ..
#rm Python-$PYTHON_VERSION.tar.xz

# TODO Remove.
#sudo ln -sfn '/usr/local/bin/python2.7' '/usr/bin/python2'
#sudo update-alternatives --install /usr/bin/python python /usr/bin/python2 1

# Install Python 2.7 essentials.
python2.7 -m ensurepip --default-pip
python2.7 -m pip install --upgrade pip setuptools wheel

# Create virtual Python 2.7 environment inside the cartoonify repository.
python2.7 -m virtualenv --python=python2.7 virtualenv
source ./virtualenv/bin/activate
cd cartoonify
pip install -r requirements_desktop.txt

# Development requirements
sudo apt install tk-dev
pip install matplotlib

cd ..
