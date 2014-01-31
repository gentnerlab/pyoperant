#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <comedilib.h>
 
#define POLLING_INTERVAL 500000        /* input polling rate in nanoseconds */
struct timespec rsi = { 0, POLLING_INTERVAL};

/* helper functions */
void do_usage()
{
  fprintf(stderr, "wait4peck usage:\n");
  fprintf(stderr, "     [-help] [-d str] [-s int] [-c int]       \n\n");
  fprintf(stderr, "        -help        = show this help message \n");
  fprintf(stderr, "        -d str       = device file handler    \n");
  fprintf(stderr, "        -s           = (int) subdevice        \n");
  fprintf(stderr, "        -c           = (int) channel          \n");
  exit(-1);
}

int command_line_parse(int argc, char **argv, char **device_fname, unsigned int *subdevice, unsigned int *channel)
{
  int i=0;
  
  for (i = 1; i < argc; i++){
    if (*argv[i] == '-'){
      if (strncmp(argv[i], "-s", 2) == 0) 
        sscanf(argv[++i], "%i", subdevice);
      else if (strncmp(argv[i], "-c", 2) == 0){
	sscanf(argv[++i], "%i", channel);
      }
      else if (strncmp(argv[i], "-help", 5) == 0){
        do_usage();
      }
      else{
        fprintf(stderr, "Unknown option: %s\t", argv[i]);
        fprintf(stderr, "Try '2ac -help'\n");
	exit(-1);
      }
    }
    else
      {
	*device_fname = argv[i];
      }

  }
  return 1;
}

/* MAIN */
int main(int argc, char *argv[])
{
	struct timeval tv;
	char buffer[30];
	char *device_fname = NULL;
	comedi_t *device;
	unsigned int subdevice;
	unsigned int channel;
	unsigned int out = 1;

	/* Parse the command line */
	command_line_parse(argc, argv, &device_fname, &subdevice, &channel); 

	/* open the comedi device */	
	device = comedi_open(device_fname);
	/* Wait for channel to go low */
	do{                                         
		nanosleep(&rsi, NULL);	               	       	
		comedi_dio_read(device, subdevice, channel, &out);
	}while (out==1);  
	
	gettimeofday(&tv, NULL);
	strftime(buffer,30,"%Y-%m-%d %T.",localtime(&tv.tv_sec));
	fprintf(stdout,"%s%ld\n",buffer,(long)tv.tv_usec);

	comedi_close(device);
	
	return 0;

}                         

