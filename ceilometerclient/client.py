#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from keystoneclient.auth.identity import v2 as v2_auth
from keystoneclient.auth.identity import v3 as v3_auth
from keystoneclient import discover
from keystoneclient import exceptions as ks_exc
from keystoneclient import session
from oslo_utils import strutils
import six.moves.urllib.parse as urlparse

from ceilometerclient.common import utils
from ceilometerclient import exc
from ceilometerclient.openstack.common.apiclient import auth
from ceilometerclient.openstack.common.apiclient import exceptions


def _discover_auth_versions(session, auth_url):
    # discover the API versions the server is supporting based on the
    # given URL
    v2_auth_url = None
    v3_auth_url = None
    try:
        ks_discover = discover.Discover(session=session, auth_url=auth_url)
        v2_auth_url = ks_discover.url_for('2.0')
        v3_auth_url = ks_discover.url_for('3.0')
    except ks_exc.DiscoveryFailure:
        raise
    except exceptions.ClientException:
        # Identity service may not support discovery. In that case,
        # try to determine version from auth_url
        url_parts = urlparse.urlparse(auth_url)
        (scheme, netloc, path, params, query, fragment) = url_parts
        path = path.lower()
        if path.startswith('/v3'):
            v3_auth_url = auth_url
        elif path.startswith('/v2'):
            v2_auth_url = auth_url
        else:
            raise exc.CommandError('Unable to determine the Keystone '
                                   'version to authenticate with '
                                   'using the given auth_url.')
    return v2_auth_url, v3_auth_url


def _get_keystone_session(**kwargs):
    # TODO(fabgia): the heavy lifting here should be really done by Keystone.
    # Unfortunately Keystone does not support a richer method to perform
    # discovery and return a single viable URL. A bug against Keystone has
    # been filed: https://bugs.launchpad.net/python-keystoneclient/+bug/1330677

    # first create a Keystone session
    cacert = kwargs.pop('cacert', None)
    cert = kwargs.pop('cert', None)
    key = kwargs.pop('key', None)
    insecure = kwargs.pop('insecure', False)
    auth_url = kwargs.pop('auth_url', None)
    project_id = kwargs.pop('project_id', None)
    project_name = kwargs.pop('project_name', None)
    timeout = kwargs.get('timeout')

    if insecure:
        verify = False
    else:
        verify = cacert or True

    if cert and key:
        # passing cert and key together is deprecated in favour of the
        # requests lib form of having the cert and key as a tuple
        cert = (cert, key)

    # create the keystone client session
    ks_session = session.Session(verify=verify, cert=cert, timeout=timeout)
    v2_auth_url, v3_auth_url = _discover_auth_versions(ks_session, auth_url)

    username = kwargs.pop('username', None)
    user_id = kwargs.pop('user_id', None)
    user_domain_name = kwargs.pop('user_domain_name', None)
    user_domain_id = kwargs.pop('user_domain_id', None)
    project_domain_name = kwargs.pop('project_domain_name', None)
    project_domain_id = kwargs.pop('project_domain_id', None)
    auth = None

    use_domain = (user_domain_id or user_domain_name or
                  project_domain_id or project_domain_name)
    use_v3 = v3_auth_url and (use_domain or (not v2_auth_url))
    use_v2 = v2_auth_url and not use_domain

    if use_v3:
        # the auth_url as v3 specified
        # e.g. http://no.where:5000/v3
        # Keystone will return only v3 as viable option
        auth = v3_auth.Password(
            v3_auth_url,
            username=username,
            password=kwargs.pop('password', None),
            user_id=user_id,
            user_domain_name=user_domain_name,
            user_domain_id=user_domain_id,
            project_name=project_name,
            project_id=project_id,
            project_domain_name=project_domain_name,
            project_domain_id=project_domain_id)
    elif use_v2:
        # the auth_url as v2 specified
        # e.g. http://no.where:5000/v2.0
        # Keystone will return only v2 as viable option
        auth = v2_auth.Password(
            v2_auth_url,
            username,
            kwargs.pop('password', None),
            tenant_id=project_id,
            tenant_name=project_name)
    else:
        raise exc.CommandError('Unable to determine the Keystone version '
                               'to authenticate with using the given '
                               'auth_url.')

    ks_session.auth = auth
    return ks_session


def _get_token_auth_ks_session(**kwargs):

    cacert = kwargs.pop('cacert', None)
    cert = kwargs.pop('cert', None)
    key = kwargs.pop('key', None)
    insecure = kwargs.pop('insecure', False)
    auth_url = kwargs.pop('auth_url', None)
    project_id = kwargs.pop('project_id', None)
    project_name = kwargs.pop('project_name', None)
    timeout = kwargs.get('timeout')
    token = kwargs['token']

    if insecure:
        verify = False
    else:
        verify = cacert or True

    if cert and key:
        # passing cert and key together is deprecated in favour of the
        # requests lib form of having the cert and key as a tuple
        cert = (cert, key)

    # create the keystone client session
    ks_session = session.Session(verify=verify, cert=cert, timeout=timeout)
    v2_auth_url, v3_auth_url = _discover_auth_versions(ks_session, auth_url)

    user_domain_name = kwargs.pop('user_domain_name', None)
    user_domain_id = kwargs.pop('user_domain_id', None)
    project_domain_name = kwargs.pop('project_domain_name', None)
    project_domain_id = kwargs.pop('project_domain_id', None)
    auth = None

    use_domain = (user_domain_id or user_domain_name or
                  project_domain_id or project_domain_name)
    use_v3 = v3_auth_url and (use_domain or (not v2_auth_url))
    use_v2 = v2_auth_url and not use_domain

    if use_v3:
        auth = v3_auth.Token(
            v3_auth_url,
            token=token,
            project_name=project_name,
            project_id=project_id,
            project_domain_name=project_domain_name,
            project_domain_id=project_domain_id)
    elif use_v2:
        auth = v2_auth.Token(
            v2_auth_url,
            token=token,
            tenant_id=project_id,
            tenant_name=project_name)
    else:
        raise exc.CommandError('Unable to determine the Keystone version '
                               'to authenticate with using the given '
                               'auth_url.')

    ks_session.auth = auth
    return ks_session


def _get_endpoint(ks_session, **kwargs):
    """Get an endpoint using the provided keystone session."""

    # set service specific endpoint types
    endpoint_type = kwargs.get('endpoint_type') or 'publicURL'
    service_type = kwargs.get('service_type') or 'metering'

    endpoint = ks_session.get_endpoint(service_type=service_type,
                                       interface=endpoint_type,
                                       region_name=kwargs.get('region_name'))

    return endpoint


class AuthPlugin(auth.BaseAuthPlugin):
    opt_names = ['tenant_id', 'region_name', 'auth_token',
                 'service_type', 'endpoint_type', 'cacert',
                 'auth_url', 'insecure', 'cert_file', 'key_file',
                 'cert', 'key', 'tenant_name', 'project_name',
                 'project_id', 'project_domain_id', 'project_domain_name',
                 'user_id', 'user_domain_id', 'user_domain_name',
                 'password', 'username', 'endpoint']

    def __init__(self, auth_system=None, **kwargs):
        self.opt_names.extend(self.common_opt_names)
        super(AuthPlugin, self).__init__(auth_system, **kwargs)

    def _do_authenticate(self, http_client):
        token = self.opts.get('token') or self.opts.get('auth_token')
        endpoint = self.opts.get('endpoint')
        if not (token and endpoint):
            ks_kwargs = self._get_ks_kwargs(http_timeout=http_client.timeout)
            ks_session = _get_keystone_session(**ks_kwargs)
            token = lambda: ks_session.get_token()
            endpoint = (self.opts.get('endpoint') or
                        _get_endpoint(ks_session, **ks_kwargs))
        self.opts['token'] = token
        self.opts['endpoint'] = endpoint

    def _get_ks_kwargs(self, http_timeout):
        project_id = (self.opts.get('project_id') or
                      self.opts.get('tenant_id'))
        project_name = (self.opts.get('project_name') or
                        self.opts.get('tenant_name'))
        ks_kwargs = {
            'username': self.opts.get('username'),
            'password': self.opts.get('password'),
            'user_id': self.opts.get('user_id'),
            'user_domain_id': self.opts.get('user_domain_id'),
            'user_domain_name': self.opts.get('user_domain_name'),
            'project_id': project_id,
            'project_name': project_name,
            'project_domain_name': self.opts.get('project_domain_name'),
            'project_domain_id': self.opts.get('project_domain_id'),
            'auth_url': self.opts.get('auth_url'),
            'cacert': self.opts.get('cacert'),
            'cert': self.opts.get('cert'),
            'key': self.opts.get('key'),
            'insecure': strutils.bool_from_string(
                self.opts.get('insecure')),
            'endpoint_type': self.opts.get('endpoint_type'),
            'region_name': self.opts.get('region_name'),
            'timeout': http_timeout,
        }
        return ks_kwargs

    def redirect_to_aodh_endpoint(self, http_timeout):
        ks_kwargs = self._get_ks_kwargs(http_timeout)
        token = self.opts.get('token') or self.opts.get('auth_token')
        # NOTE(liusheng): if token provided, we try to get keystone session
        # with token, else, we get keystone session with user info and
        # password. And then use the keystone session to get aodh's endpoint.
        if token:
            token = token() if callable(token) else token
            ks_kwargs.update(token=token)
            ks_session = _get_token_auth_ks_session(**ks_kwargs)
        else:
            ks_session = _get_keystone_session(**ks_kwargs)
        ks_kwargs.update(service_type='alarming')
        self.opts['endpoint'] = _get_endpoint(ks_session, **ks_kwargs)

    def token_and_endpoint(self, endpoint_type, service_type):
        token = self.opts.get('token')
        if callable(token):
            token = token()
        return token, self.opts.get('endpoint')

    def sufficient_options(self):
        """Check if all required options are present.

        :raises: AuthPluginOptionsMissing
        """
        has_token = self.opts.get('token') or self.opts.get('auth_token')
        no_auth = has_token and self.opts.get('endpoint')
        has_tenant = self.opts.get('tenant_id') or self.opts.get('tenant_name')
        has_credential = (self.opts.get('username') and has_tenant
                          and self.opts.get('password')
                          and self.opts.get('auth_url'))
        missing = not (no_auth or has_credential)
        if missing:
            missing_opts = []
            opts = ['token', 'endpoint', 'username', 'password', 'auth_url',
                    'tenant_id', 'tenant_name']
            for opt in opts:
                if not self.opts.get(opt):
                    missing_opts.append(opt)
            raise exceptions.AuthPluginOptionsMissing(missing_opts)


def _adjust_kwargs(kwargs):
    client_kwargs = {
        'username': kwargs.get('os_username'),
        'password': kwargs.get('os_password'),
        'tenant_id': kwargs.get('os_tenant_id'),
        'tenant_name': kwargs.get('os_tenant_name'),
        'auth_url': kwargs.get('os_auth_url'),
        'region_name': kwargs.get('os_region_name'),
        'service_type': kwargs.get('os_service_type'),
        'endpoint_type': kwargs.get('os_endpoint_type'),
        'insecure': kwargs.get('os_insecure'),
        'cacert': kwargs.get('os_cacert'),
        'cert_file': kwargs.get('os_cert'),
        'key_file': kwargs.get('os_key'),
        'token': kwargs.get('os_token') or kwargs.get('os_auth_token'),
        'user_domain_name': kwargs.get('os_user_domain_name'),
        'user_domain_id': kwargs.get('os_user_domain_id'),
        'project_domain_name': kwargs.get('os_project_domain_name'),
        'project_domain_id': kwargs.get('os_project_domain_id'),
    }

    client_kwargs.update(kwargs)
    client_kwargs['token'] = kwargs.get('token') or kwargs.get('auth_token')

    timeout = kwargs.get('timeout')
    if timeout is not None:
        timeout = int(timeout)
        if timeout <= 0:
            timeout = None

    insecure = strutils.bool_from_string(kwargs.get('insecure'))
    verify = kwargs.get('verify')
    if verify is None:
        if insecure:
            verify = False
        else:
            verify = client_kwargs.get('cacert') or True

    cert = client_kwargs.get('cert_file')
    key = client_kwargs.get('key_file')
    if cert and key:
        cert = cert, key

    client_kwargs.update({'verify': verify, 'cert': cert, 'timeout': timeout})
    return client_kwargs


def Client(version, *args, **kwargs):
    client_kwargs = _adjust_kwargs(kwargs)

    module = utils.import_versioned_module(version, 'client')
    client_class = getattr(module, 'Client')
    return client_class(*args, **client_kwargs)


def get_client(version, **kwargs):
    """Get an authenticated client, based on the credentials in the kwargs.

    :param api_version: the API version to use ('1' or '2')
    :param kwargs: keyword args containing credentials, either:

            * os_auth_token: (DEPRECATED) pre-existing token to re-use,
                             use os_token instead
            * os_token: pre-existing token to re-use
            * ceilometer_url: (DEPRECATED) Ceilometer API endpoint,
                              use os_endpoint instead
            * os_endpoint: Ceilometer API endpoint

            or:

            * os_username: name of user
            * os_password: user's password
            * os_user_id: user's id
            * os_user_domain_id: the domain id of the user
            * os_user_domain_name: the domain name of the user
            * os_project_id: the user project id
            * os_tenant_id: V2 alternative to os_project_id
            * os_project_name: the user project name
            * os_tenant_name: V2 alternative to os_project_name
            * os_project_domain_name: domain name for the user project
            * os_project_domain_id: domain id for the user project
            * os_auth_url: endpoint to authenticate against
            * os_cert|os_cacert: path of CA TLS certificate
            * os_key: SSL private key
            * os_insecure: allow insecure SSL (no cert verification)
    """
    endpoint = kwargs.get('os_endpoint') or kwargs.get('ceilometer_url')

    return Client(version, endpoint, **kwargs)


def get_auth_plugin(endpoint, **kwargs):
    auth_plugin = AuthPlugin(
        auth_url=kwargs.get('auth_url'),
        service_type=kwargs.get('service_type'),
        token=kwargs.get('token'),
        endpoint_type=kwargs.get('endpoint_type'),
        insecure=kwargs.get('insecure'),
        region_name=kwargs.get('region_name'),
        cacert=kwargs.get('cacert'),
        tenant_id=kwargs.get('project_id') or kwargs.get('tenant_id'),
        endpoint=endpoint,
        username=kwargs.get('username'),
        password=kwargs.get('password'),
        tenant_name=kwargs.get('tenant_name') or kwargs.get('project_name'),
        user_domain_name=kwargs.get('user_domain_name'),
        user_domain_id=kwargs.get('user_domain_id'),
        project_domain_name=kwargs.get('project_domain_name'),
        project_domain_id=kwargs.get('project_domain_id')
    )
    return auth_plugin
