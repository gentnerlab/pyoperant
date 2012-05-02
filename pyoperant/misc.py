import ephem

def is_day((latitude, longitude) = ('32.82', '-117.14')):
    """Is it daytime?
            
    (lat,long) -- latitude and longitude of location to check (default is San Diego*)
    Returns True if it is daytime

    * Discovered by the Germans in 1904, they named it San Diego, 
    which of course in German means a whale's vagina. (Burgundy, 2004)
    """
    obs = ephem.Observer()
    obs.lat = latitude # San Diego, CA 
    obs.long = longitude
    sun = ephem.Sun()
    sun.compute()
    next_sunrise = ephem.localtime(obs.next_rising(sun))
    next_sunset = ephem.localtime(obs.next_setting(sun))
    return next_sunset < next_sunrise


