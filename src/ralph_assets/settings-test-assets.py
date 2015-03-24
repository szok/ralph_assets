"""A testing profile."""

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'ralph',
        'USER': 'root',
        'HOST': 'localhost',
    },
}

PLUGGABLE_APPS = ['cmdb', 'assets']

SOUTH_TESTS_MIGRATE = False

ASSETS_AUTO_ASSIGN_HOSTNAME = True
