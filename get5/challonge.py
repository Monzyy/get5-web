from requests import request, HTTPError
import itertools

from get5 import config_setting

BASE_URL="https://api.challonge.com/v1/"

class ChallongeException(Exception):
    pass

class ChallongeClient(object):

    def fetch(self, method, uri, params_prefix=None, **params):
        """Fetch the given uri and return the contents of the response."""
        url = "{}{}.json".format(BASE_URL, uri)
        params = self._prepare_params(params, params_prefix)
        if method.lower() == 'get':
            params['api_key'] = config_setting('CHALLONGE_API_KEY')
            r_data = {"params": params}
        else:
            r_data = {"data": params, "params": {'api_key': config_setting('CHALLONGE_API_KEY')}}
        try:
            response = request(
                method,
                url,
                **r_data)
            response.raise_for_status()
        except HTTPError:
            # wrap up application-level errors
            doc = response.json()
            if doc.get("errors"):
                raise ChallongeException(*doc['errors'])

        return response.json()


    def _prepare_params(self, dirty_params, prefix=None):
        """Prepares parameters to be sent to challonge.com.
        The `prefix` can be used to convert parameters with keys that
        look like ("name", "url", "tournament_type") into something like
        ("tournament[name]", "tournament[url]", "tournament[tournament_type]"),
        which is how challonge.com expects parameters describing specific
        objects.
        """
        if prefix and prefix.endswith('[]'):
            keys = []
            values = []
            for k, v in dirty_params.items():
                if isinstance(v, (tuple, list)):
                    keys.append(k)
                    values.append(v)
            firstiter = ((k, v) for vals in zip(*values) for k, v in zip(keys, vals))
            lastiter = ((k, v) for k, v in dirty_params.items() if k not in keys)
            dpiter = itertools.chain(firstiter, lastiter)
        else:
            dpiter = dirty_params.items()

        params = {}
        for k, v in dpiter:
            if isinstance(v, (tuple, list)):
                for val in v:
                    val = _prepare_value(val)
                    if prefix:
                        params["{}[{}][]".format(prefix, k)] = val
                    else:
                        params[k + "[]"] = val
            else:
                v = self._prepare_value(v)
                if prefix:
                    params["{}[{}]".format(prefix, k)] = v
                else:
                    params[k] = v

        return params

    def _prepare_value(self, val):
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        elif isinstance(val, bool):
            # challonge.com only accepts lowercase true/false
            val = str(val).lower()
        return val

    @property
    def tournaments(self):
        return self.fetch('get', 'tournaments')

    def tournament(self, id, include_participants=True, include_matches=True):
        include_participants = 1 if include_participants else 0
        include_matches = 1 if include_matches else 0
        return self.fetch('get', 'tournaments/{}'.format(id),
                          include_matches=include_matches,
                          include_participants=include_participants)

    def create_tournament(self, name, url, private=True, open_signup=True, **kwargs):
        return self.fetch('post', 'tournaments',
                          params_prefix='tournament',
                          name=name, url=url, private=private,
                          open_signup=open_signup, game_id=194, **kwargs)

    def delete_tournament(self, id):
        val = self.fetch('delete', 'tournaments/{}'.format(id))
        return val

    def start_tournament(self, id):
        val = self.fetch('post', 'tournaments/{}/start'.format(id), include_matches=1)
        return val

    def reset_tournament(self, id):
        val = self.fetch('post', 'tournaments/{}/reset'.format(id))
        return val

    def participants(self, tournament_id):
        return self.fetch('get', 'tournaments/{}/participants'.format(tournament_id))

    def participant(self, id):
        return self.fetch('get', 'tournaments/{}/participants'.format(tournament_id))

    def update_participant_misc(self, tournament_id, id, misc):
        return self.fetch('put', 'tournaments/{}/participants/{}'.format(tournament_id, id),
                          params_prefix='participant', misc=str(misc))

    def update_match(self, tournament_id, id, **kwargs):
        return self.fetch('put', 'tournaments/{}/matches/{}'.format(tournament_id, id),
                          params_prefix='match', **kwargs)
