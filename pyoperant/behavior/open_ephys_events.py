def check_open_ephys(parameters):
    if "conn_open_ephys" in parameters.keys():
        if parameters["conn_open_ephys"] == "True":
            return True