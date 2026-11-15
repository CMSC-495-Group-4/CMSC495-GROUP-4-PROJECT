# CMSC 495 - Group 4 Project

University of Maryland Global Campus

## Project Description
Collaborative computer science capstone project
for CMSC 495.

## Run the alpha

Install the project's dependencies and start Flask:

```powershell
python -m pip install -r requirements.txt
python app.py
```

On first start, the app creates `instance/campuspath.db` from
[`database/schema.sql`](./database/schema.sql). Set the `DATABASE_NAME`
environment variable to use a different SQLite file. The database is local
and is excluded from version control.

The alpha does not include campus records. Add real building and pathway data
before routing is available. The UI will report when the database has no
locations. The old `campus.db` format is not migrated automatically; back up
and migrate any existing data before pointing `DATABASE_NAME` at that file.

## API

- `GET /api/locations` returns the configured buildings.
- `POST /api/route` accepts JSON such as
  `{"startId": 1, "destinationId": 2, "accessible": true}`.
- Routes use Dijkstra's algorithm with pathway distance as the weight.
  Pathways are treated as bidirectional. Accessible requests exclude pathways
  with stairs or without wheelchair access.
- The displayed walking time is a distance-based estimate (75 meters/minute),
  not a trained model prediction. `TravelTimeObservations` stores actual
  observations for future model training; scikit-learn is not needed yet.

## Team Roles
- Lead Architect
- Interface Designer
- Integration Lead

## Development Workflow
Team members work in separate feature branches
and submit pull requests for review before
merging into main.
