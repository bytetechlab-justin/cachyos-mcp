import json
from ..security import Denied

async def json_command(r, argv):
    result = await r.run(argv)
    if result['success']:
        try:
            result['data'] = json.loads(result['stdout'])
        except ValueError:
            result.update(success=False, error='invalid_utility_json')
    return result


def limit(value: int, maximum=1000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise Denied(f'limit must be between 1 and {maximum}')
    return value
