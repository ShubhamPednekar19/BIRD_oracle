COMMENT ON COLUMN circuits.circuitId IS 'unique identification number of the circuit';
COMMENT ON COLUMN circuits.circuitRef IS 'circuit reference name';
COMMENT ON COLUMN circuits."name" IS 'full name of circuit';
COMMENT ON COLUMN circuits."location" IS 'location of circuit';
COMMENT ON COLUMN circuits.country IS 'country of circuit';
COMMENT ON COLUMN circuits.lat IS 'latitude of location of circuit';
COMMENT ON COLUMN circuits.lng IS 'longitude of location of circuit';
ALTER TABLE circuits MODIFY (lng ANNOTATIONS (ADD value_description 'commonsense evidence: Location coordinates: (lat, lng)'));
ALTER TABLE circuits MODIFY (alt ANNOTATIONS (ADD value_description 'not useful'));
COMMENT ON COLUMN circuits.url IS 'url';

COMMENT ON COLUMN constructorResults.constructorResultsId IS 'constructor Results Id';
COMMENT ON COLUMN constructorResults.raceId IS 'race id';
COMMENT ON COLUMN constructorResults.constructorId IS 'constructor id';
COMMENT ON COLUMN constructorResults.points IS 'points';
COMMENT ON COLUMN constructorResults."status" IS 'status';

COMMENT ON COLUMN constructorStandings.constructorStandingsId IS 'unique identification of the constructor standing records';
COMMENT ON COLUMN constructorStandings.raceId IS 'id number identifying which races';
COMMENT ON COLUMN constructorStandings.constructorId IS 'id number identifying which id';
COMMENT ON COLUMN constructorStandings.points IS 'how many points acquired in each race';
COMMENT ON COLUMN constructorStandings."position" IS 'position or track of circuits';
ALTER TABLE constructorStandings MODIFY (positionText ANNOTATIONS (ADD value_description 'same with position, not quite useful'));
COMMENT ON COLUMN constructorStandings.wins IS 'wins';

COMMENT ON COLUMN constructors.constructorId IS 'the unique identification number identifying constructors';
COMMENT ON COLUMN constructors.constructorRef IS 'Constructor Reference name';
COMMENT ON COLUMN constructors."name" IS 'full name of the constructor';
COMMENT ON COLUMN constructors.nationality IS 'nationality of the constructor';
COMMENT ON COLUMN constructors.url IS 'the introduction website of the constructor';
ALTER TABLE constructors MODIFY (url ANNOTATIONS (ADD value_description 'commonsense evidence: How to find out the detailed introduction of the constructor: through its url'));

COMMENT ON COLUMN driverStandings.driverStandingsId IS 'the unique identification number identifying driver standing records';
COMMENT ON COLUMN driverStandings.raceId IS 'id number identifying which races';
COMMENT ON COLUMN driverStandings.driverId IS 'id number identifying which drivers';
COMMENT ON COLUMN driverStandings.points IS 'how many points acquired in each race';
COMMENT ON COLUMN driverStandings."position" IS 'position or track of circuits';
COMMENT ON COLUMN driverStandings.wins IS 'wins';
ALTER TABLE driverStandings MODIFY (positionText ANNOTATIONS (ADD value_description 'same with position, not quite useful'));

COMMENT ON COLUMN drivers.driverId IS 'the unique identification number identifying each driver';
COMMENT ON COLUMN drivers.driverRef IS 'driver reference name';
COMMENT ON COLUMN drivers."number" IS 'number';
COMMENT ON COLUMN drivers.code IS 'abbreviated code for drivers';
ALTER TABLE drivers MODIFY (code ANNOTATIONS (ADD value_description 'if "null" or empty, it means it doesn''t have code'));
COMMENT ON COLUMN drivers.forename IS 'forename';
COMMENT ON COLUMN drivers.surname IS 'surname';
COMMENT ON COLUMN drivers.dob IS 'date of birth';
COMMENT ON COLUMN drivers.nationality IS 'nationality of drivers';
COMMENT ON COLUMN drivers.url IS 'the introduction website of the drivers';

COMMENT ON COLUMN lapTimes.raceId IS 'the identification number identifying race';
COMMENT ON COLUMN lapTimes.driverId IS 'the identification number identifying each driver';
COMMENT ON COLUMN lapTimes.lap IS 'lap number';
COMMENT ON COLUMN lapTimes."position" IS 'position or track of circuits';
COMMENT ON COLUMN lapTimes."time" IS 'lap time';
ALTER TABLE lapTimes MODIFY ("time" ANNOTATIONS (ADD value_description 'in minutes / seconds / ...'));
COMMENT ON COLUMN lapTimes.milliseconds IS 'milliseconds';

COMMENT ON COLUMN pitStops.raceId IS 'the identification number identifying race';
COMMENT ON COLUMN pitStops.driverId IS 'the identification number identifying each driver';
COMMENT ON COLUMN pitStops."stop" IS 'stop number';
COMMENT ON COLUMN pitStops.lap IS 'lap number';
COMMENT ON COLUMN pitStops."time" IS 'time';
ALTER TABLE pitStops MODIFY ("time" ANNOTATIONS (ADD value_description 'exact time'));
COMMENT ON COLUMN pitStops.duration IS 'duration time';
ALTER TABLE pitStops MODIFY (duration ANNOTATIONS (ADD value_description 'seconds/'));
COMMENT ON COLUMN pitStops.milliseconds IS 'milliseconds';

COMMENT ON COLUMN qualifying.qualifyId IS 'the unique identification number identifying qualifying';
ALTER TABLE qualifying MODIFY (qualifyId ANNOTATIONS (ADD value_description 'How does F1 Sprint qualifying work? Sprint qualifying is essentially a short-form Grand Prix  a race that is one-third the number of laps of the main event on Sunday. However, the drivers are battling for positions on the grid for the start of Sunday''s race.'));
COMMENT ON COLUMN qualifying.raceId IS 'the identification number identifying each race';
COMMENT ON COLUMN qualifying.driverId IS 'the identification number identifying each driver';
COMMENT ON COLUMN qualifying.constructorId IS 'constructor Id';
COMMENT ON COLUMN qualifying."number" IS 'number';
COMMENT ON COLUMN qualifying."position" IS 'position or track of circuit';
COMMENT ON COLUMN qualifying.q1 IS 'time in qualifying 1';
ALTER TABLE qualifying MODIFY (q1 ANNOTATIONS (ADD value_description 'in minutes / seconds / ... commonsense evidence: Q1 lap times determine pole position and the order of the front 10 positions on the grid. The slowest driver in Q1 starts 10th, the next starts ninth and so on. All 20 F1 drivers participate in the first period, called Q1, with each trying to set the fastest time possible. Those in the top 15 move on to the next period of qualifying, called Q2. The five slowest drivers are eliminated and will start the race in the last five positions on the grid.'));
COMMENT ON COLUMN qualifying.q2 IS 'time in qualifying 2';
ALTER TABLE qualifying MODIFY (q2 ANNOTATIONS (ADD value_description 'in minutes / seconds / ... commonsense evidence: only top 15 in the q1 has the record of q2 Q2 is slightly shorter but follows the same format. Drivers try to put down their best times to move on to Q1 as one of the 10 fastest cars. The five outside of the top 10 are eliminated and start the race from 11th to 15th based on their best lap time.'));
COMMENT ON COLUMN qualifying.q3 IS 'time in qualifying 3';
ALTER TABLE qualifying MODIFY (q3 ANNOTATIONS (ADD value_description 'in minutes / seconds / ... commonsense evidence: only top 10 in the q2 has the record of q3'));

COMMENT ON COLUMN races.raceId IS 'the unique identification number identifying the race';
COMMENT ON COLUMN races."year" IS 'year';
COMMENT ON COLUMN races.round IS 'round';
COMMENT ON COLUMN races.circuitId IS 'circuit Id';
COMMENT ON COLUMN races."name" IS 'name of the race';
COMMENT ON COLUMN races."date" IS 'duration time';
COMMENT ON COLUMN races."time" IS 'time of the location';
COMMENT ON COLUMN races.url IS 'introduction of races';

COMMENT ON COLUMN results.resultId IS 'the unique identification number identifying race result';
COMMENT ON COLUMN results.raceId IS 'the identification number identifying the race';
COMMENT ON COLUMN results.driverId IS 'the identification number identifying the driver';
COMMENT ON COLUMN results.constructorId IS 'the identification number identifying which constructors';
COMMENT ON COLUMN results."number" IS 'number';
COMMENT ON COLUMN results.grid IS 'the number identifying the area where cars are set into a grid formation in order to start the race.';
COMMENT ON COLUMN results."position" IS 'The finishing position or track of circuits';
ALTER TABLE results MODIFY (positionText ANNOTATIONS (ADD value_description 'not quite useful'));
COMMENT ON COLUMN results.positionOrder IS 'the finishing order of positions';
COMMENT ON COLUMN results.points IS 'points';
COMMENT ON COLUMN results.laps IS 'lap number';
COMMENT ON COLUMN results."time" IS 'finish time';
ALTER TABLE results MODIFY ("time" ANNOTATIONS (ADD value_description 'commonsense evidence: 1. if the value exists, it means the driver finished the race. 2. Only the time of the champion shows in the format of "minutes: seconds.millionsecond", the time of the other drivers shows as "seconds.millionsecond" , which means their actual time is the time of the champion adding the value in this cell.'));
COMMENT ON COLUMN results.milliseconds IS 'the actual finishing time of drivers in milliseconds';
ALTER TABLE results MODIFY (milliseconds ANNOTATIONS (ADD value_description 'the actual finishing time of drivers'));
COMMENT ON COLUMN results.fastestLap IS 'fastest lap number';
COMMENT ON COLUMN results."rank" IS 'starting rank positioned by fastest lap speed';
COMMENT ON COLUMN results.fastestLapTime IS 'fastest Lap Time';
ALTER TABLE results MODIFY (fastestLapTime ANNOTATIONS (ADD value_description 'faster (smaller in the value) "fastestLapTime" leads to higher rank (smaller is higher rank)'));
COMMENT ON COLUMN results.fastestLapSpeed IS 'fastest Lap Speed';
ALTER TABLE results MODIFY (fastestLapSpeed ANNOTATIONS (ADD value_description '(km / h)'));
COMMENT ON COLUMN results.statusId IS 'status ID';
ALTER TABLE results MODIFY (statusId ANNOTATIONS (ADD value_description 'its category description appear in the table status'));

COMMENT ON COLUMN seasons."year" IS 'the unique identification number identifying the race';
COMMENT ON COLUMN seasons.url IS 'website link of season race introduction';

COMMENT ON COLUMN "status".statusId IS 'the unique identification number identifying status';
COMMENT ON COLUMN "status"."status" IS 'full name of status';
