import sys

from ralph.settings import *  # noqa

# for dhcp agent test
sys.path.append(os.path.join(BASE_DIR, '..', '..', 'contrib', 'dhcp_agent'))

DEBUG = False

TEST_DB_ENGINE = os.environ.get('TEST_DB_ENGINE', 'sqlite')

if TEST_DB_ENGINE == 'mysql':
    # use default mysql settings
    if not os.environ.get('DATABASE_PASSWORD'):
        DATABASES['default']['PASSWORD'] = None
elif TEST_DB_ENGINE == 'psql':
    DATABASES['default'].update({
        'ENGINE': 'transaction_hooks.backends.postgresql_psycopg2',
        'PORT': os.environ.get('DATABASE_PORT', 5432),
        'OPTIONS': {},
    })
else:  # use sqlite as default
    DATABASES = {
        'default': {
            'ENGINE': 'transaction_hooks.backends.sqlite3',
            'NAME': ':memory:',
            'ATOMIC_REQUESTS': True,
        }
    }

INSTALLED_APPS += (
    'ralph.lib.mixins',
    'ralph.tests',
    'ralph.lib.custom_fields.tests',
    'ralph.lib.permissions.tests',
    'ralph.lib.polymorphic.tests',
    'ralph.lib.mixins.tests',
)

USE_CACHE = False
PASSWORD_HASHERS = ('django_plainpasswordhasher.PlainPasswordHasher',)
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

ROOT_URLCONF = 'ralph.urls.test'
# specify all url modules to reload during specific tests
# see `ralph.tests.mixins.ReloadUrlsMixin` for details
URLCONF_MODULES = ['ralph.urls.base', ROOT_URLCONF]

# Uncomment lines below if you want some additional output from loggers
# during tests.
# LOGGING['loggers']['ralph'].update(
#     {'level': 'DEBUG', 'handlers': ['console']}
# )

RQ_QUEUES['ralph_job_test'] = dict(ASYNC=False, **REDIS_CONNECTION)
RQ_QUEUES['ralph_async_transitions']['ASYNC'] = False
RALPH_INTERNAL_SERVICES.update({
    'JOB_TEST': {
        'queue_name': 'ralph_job_test',
        'method': 'ralph.lib.external_services.tests.test_job_func',
    }
})

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    },
    'template_fragments': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

SKIP_MIGRATIONS = os.environ.get('SKIP_MIGRATIONS', None)
if SKIP_MIGRATIONS:
    print('skipping migrations')

    class DisableMigrations(object):

        def __contains__(self, item):
            return True

        def __getitem__(self, item):
            return "notmigrations"

    MIGRATION_MODULES = DisableMigrations()

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
ENABLE_EMAIL_NOTIFICATION = True

ENABLE_HERMES_INTEGRATION = True
HERMES['ENABLED'] = ENABLE_HERMES_INTEGRATION
