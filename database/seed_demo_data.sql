-- Demo-only routes for six residence halls/community locations.
-- Building point coordinates come from the UMD Campus Map BuildingPoint
-- layer (used for map labels, not verified entrances):
-- https://maps.umd.edu/map/
-- https://services9.arcgis.com/1rOwFRpAwrxe0rBl/arcgis/rest/services/CampusMapDefault_NoInsite/FeatureServer/4
-- Path distances, traffic patterns, and accessibility flags below are
-- simulated and must not be used as real pedestrian or accessibility guidance.

PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

INSERT INTO Buildings
    (building_id, building_name, latitude, longitude, description,
     wheelchair_accessible)
VALUES
    (122, 'Cumberland Hall (122 CBD)', 38.99225327, -76.94397454,
     'Address: 4250 Farm Drive, College Park, MD 20742. UMD Campus Map BuildingPoint label coordinate; entrance not verified. Demo accessibility flag is simulated.',
     1),
    (96, 'Cambridge Hall (096 CAM)', 38.99171630, -76.94303926,
     'Address: 4230 Farm Drive, College Park, MD 20742. UMD Campus Map BuildingPoint label coordinate; entrance not verified. Demo accessibility flag is simulated.',
     1),
    (98, 'Centreville Hall (098 CEN)', 38.99225105, -76.94211076,
     'Address: 4243 Valley Drive, College Park, MD 20742. UMD Campus Map BuildingPoint label coordinate; entrance not verified. Demo accessibility flag is simulated.',
     1),
    (99, 'Bel Air Hall (099 BEL)', 38.99280739, -76.94262314,
     'Address: 4213 Valley Drive, College Park, MD 20742. UMD Campus Map BuildingPoint label coordinate; entrance not verified. Demo accessibility flag is simulated.',
     1),
    (121, 'Chestertown Hall (121 CHS)', 38.99280774, -76.94345911,
     'Address: 4201 Valley Drive, College Park, MD 20742. UMD Campus Map BuildingPoint label coordinate; entrance not verified. Demo accessibility flag is simulated.',
     1),
    (97, 'Cambridge Community Center (097 CCC)', 38.99220390, -76.94304089,
     'Address: 4232 Farm Drive, College Park, MD 20742. UMD Campus Map BuildingPoint label coordinate; entrance not verified. Demo accessibility flag is simulated.',
     1)
ON CONFLICT (building_id) DO UPDATE SET
    building_name = excluded.building_name,
    latitude = excluded.latitude,
    longitude = excluded.longitude,
    description = excluded.description,
    wheelchair_accessible = excluded.wheelchair_accessible;

INSERT INTO Pathways
    (pathway_id, start_building_id, end_building_id, distance_meters,
     foot_traffic, has_stairs, wheelchair_accessible)
VALUES
    (201, 122, 97, 95,  'medium', 0, 1),
    (202, 97, 98, 90,   'low',    0, 1),
    (203, 98, 99, 100,  'high',   1, 0),
    (204, 99, 121, 100, 'medium', 0, 1),
    (205, 121, 122, 130,'low',    0, 1),
    (206, 96, 97, 70,   'low',    0, 1),
    (207, 96, 98, 130,  'medium', 1, 0),
    (208, 96, 121, 115, 'high',   0, 1)
ON CONFLICT (pathway_id) DO UPDATE SET
    start_building_id = excluded.start_building_id,
    end_building_id = excluded.end_building_id,
    distance_meters = excluded.distance_meters,
    foot_traffic = excluded.foot_traffic,
    has_stairs = excluded.has_stairs,
    wheelchair_accessible = excluded.wheelchair_accessible;

INSERT INTO PathwayTraffic (pathway_id, time_period, foot_traffic)
VALUES
    (201, 'morning', 'high'),   (201, 'midday', 'medium'), (201, 'evening', 'low'),
    (202, 'morning', 'medium'), (202, 'midday', 'low'),   (202, 'evening', 'medium'),
    (203, 'morning', 'high'),   (203, 'midday', 'high'),  (203, 'evening', 'low'),
    (204, 'morning', 'medium'), (204, 'midday', 'high'),  (204, 'evening', 'low'),
    (205, 'morning', 'low'),    (205, 'midday', 'medium'),(205, 'evening', 'high'),
    (206, 'morning', 'high'),   (206, 'midday', 'medium'),(206, 'evening', 'low'),
    (207, 'morning', 'high'),   (207, 'midday', 'low'),   (207, 'evening', 'medium'),
    (208, 'morning', 'low'),    (208, 'midday', 'high'),  (208, 'evening', 'medium')
ON CONFLICT (pathway_id, time_period) DO UPDATE SET
    foot_traffic = excluded.foot_traffic;

COMMIT;
