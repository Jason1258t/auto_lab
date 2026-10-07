"""Print the API description (OpenAPI JSON). The frontend generates its
TypeScript types from it: `npm run api:types` in frontend/."""

import json

from autolab.api.app import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=1, sort_keys=True))
