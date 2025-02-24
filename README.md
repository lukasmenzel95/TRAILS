# TREAD
This project analyzes off-road (gravel) cycling terrain using video/photo and GPS data  By classifying surface types (gravel, dirt, asphalt) from ride footage, it maps conditions to specific locations. The system provides post-ride insights to help cyclists choose the best tires for grip and performance based on real riding conditions.

## Project Concept & Basic Approach

Goal:
	•	Create a system to classify off-road (gravel) cycling terrain from images or video frames, correlate it with GPS data, and visualize results (e.g., on a map).
	•	Possibly integrate with OpenStreetMaps

Key Observations:
	•	Video + GPS: Extract frames from bike-ride videos, match each frame to its GPS coordinate (by timestamp).
	•	Data Flow:
	1.	Record the ride (video + GPS).
	2.	Extract frames (images).
	3.	Classify surfaces (e.g., “gravel,” “dirt,” “asphalt”).
	4.	Visualize on a map (Leaflet/Mapbox) for post-ride analysis.
