import sys, os
# Add project root to path so `import app` works from the tests/ subdirectory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ['DATABASE_URL'] = 'postgresql://fake:fake@localhost/fake'
os.environ['AUTH_USER'] = 'usuario_test'
os.environ['AUTH_PASS'] = 'clave_test'
