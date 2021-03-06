// $Id: raw_listen.c,v 1.5 2004/03/12 22:05:54 idgay Exp $

/*									tab:4
 * "Copyright (c) 2000-2003 The Regents of the University  of California.  
 * All rights reserved.
 *
 * Permission to use, copy, modify, and distribute this software and its
 * documentation for any purpose, without fee, and without written agreement is
 * hereby granted, provided that the above copyright notice, the following
 * two paragraphs and the author appear in all copies of this software.
 * 
 * IN NO EVENT SHALL THE UNIVERSITY OF CALIFORNIA BE LIABLE TO ANY PARTY FOR
 * DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING OUT
 * OF THE USE OF THIS SOFTWARE AND ITS DOCUMENTATION, EVEN IF THE UNIVERSITY OF
 * CALIFORNIA HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 * 
 * THE UNIVERSITY OF CALIFORNIA SPECIFICALLY DISCLAIMS ANY WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE.  THE SOFTWARE PROVIDED HEREUNDER IS
 * ON AN "AS IS" BASIS, AND THE UNIVERSITY OF CALIFORNIA HAS NO OBLIGATION TO
 * PROVIDE MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS."
 *
 * Copyright (c) 2002-2003 Intel Corporation
 * All rights reserved.
 *
 * This file is distributed under the terms in the attached INTEL-LICENSE     
 * file. If you do not find these files, copies can be found by writing to
 * Intel Research Berkeley, 2150 Shattuck Avenue, Suite 1300, Berkeley, CA, 
 * 94704.  Attention:  Intel License Inquiry.
 */

/*
 * read debug packets from tmote sky motes over serial 
 * and print to stdout
 *
 * cobbled together from raw_listen.c from tinyos-1.x tools folder
 * and the original python script to do the same thing by Darren Bishop
 *
 * this mess by Alan Medlar
 */

#include <sys/types.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <termios.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#ifdef __CYGWIN__
#include <windows.h>  // i don't have a winbox to test this on :-(
#endif

#define BAUDRATE B57600
#define SERIAL_DEVICE "/dev/hen/motes/USB0"

#define SYNC_BYTE 0x7e
#define ESCAPE_BYTE 0x7d
#define HEADER_LENGTH 10
#define TOSH_DATA_LENGTH 50

int input_stream;

void print_usage(char *name);
void open_input(int argc, char **argv);

int main(int argc, char ** argv) {
//    int n = 0;
    unsigned char c;
    int cnt, 
	insync = 0, 
	count = 0, 
	escaped = 0;
    char packet[HEADER_LENGTH + TOSH_DATA_LENGTH + 2];
    fd_set fds;

    if (argc > 3 || (argc > 1 && argv[1][0] == '-')) {
	print_usage(argv[0]);
	exit(2);
    }

    open_input(argc, argv);

    while(1) { 
//	unsigned char c;
//	int cnt = read(input_stream, &c, 1);

	FD_ZERO(&fds);
        FD_SET(input_stream, &fds);
        cnt = select(input_stream + 1, &fds, NULL, NULL, NULL);

	if(cnt < 0) {
	    printf("select returned %i\n", cnt);
	    fflush(stdout);
	    continue;
	}
	
        cnt = read(input_stream, &c, 1);

	if (cnt < 0) {
	    perror("error reading from serial port");
	    exit(2);
	}
	if (cnt == 1) {
//	    if (c == 0x7e || ++n == 26) {
//		n = 0;
//		printf("\n");
//	    }
//	    printf("%c", c);
//	    fflush(stdout);


	    // each packet has a SYNC_BYTE at the beginning and end
	    if(c == SYNC_BYTE) {
		// start of frame
		if(insync == 0) {
		    insync = 1;
		    count = 0;
		    continue;
		}
		if(count < HEADER_LENGTH) { // empty packet
		    insync = escaped = count = 0;
		    continue;
		}
		// end of frame
		// print packet contents, reset vars
		packet[count-2] = '\0';
		printf("%s\n", &packet[HEADER_LENGTH+1]);
		fflush(stdout);
		insync = escaped = count = 0;
	    }
	    if(insync == 0) {
	    	continue;
	    }
	    if(c == ESCAPE_BYTE && !escaped) {
	    	escaped = 1;
		continue;
	    }
	    if(escaped) {
	    	escaped = 0;
		if(c == SYNC_BYTE || c == ESCAPE_BYTE) {
		    insync = 0;
		    continue;
		}
		c = c ^ 0x20;
	    }

	    packet[count++] = c;
	}
    }
}

void print_usage(char *name){
    //usage...
    fprintf(stderr, "usage: %s [serial port] [baudrate]\n", name);
    fprintf(stderr, "Default serial port is " SERIAL_DEVICE ", default baud rate is 57600\n");
}


void open_input(int argc, char **argv) {
    /* open input_stream for read/write */ 
    struct termios newtio;
    const char *name = SERIAL_DEVICE;
    unsigned long baudrate = BAUDRATE;

    if (argc > 1)
	name = argv[1];
    if (argc > 2) {
	int reqrate = atoi(argv[2]);

	switch (reqrate) {
#ifdef B50
	case 50: baudrate = B50; break;
#endif
#ifdef B75
	case 75: baudrate = B75; break;
#endif
#ifdef B110
	case 110: baudrate = B110; break;
#endif
#ifdef B134
	case 134: baudrate = B134; break;
#endif
#ifdef B150
	case 150: baudrate = B150; break;
#endif
#ifdef B200
	case 200: baudrate = B200; break;
#endif
#ifdef B300
	case 300: baudrate = B300; break;
#endif
#ifdef B600
	case 600: baudrate = B600; break;
#endif
#ifdef B1200
	case 1200: baudrate = B1200; break;
#endif
#ifdef B1800
	case 1800: baudrate = B1800; break;
#endif
#ifdef B2400
	case 2400: baudrate = B2400; break;
#endif
#ifdef B4800
	case 4800: baudrate = B4800; break;
#endif
#ifdef B9600
	case 9600: baudrate = B9600; break;
#endif
#ifdef B19200
	case 19200: baudrate = B19200; break;
#endif
#ifdef B38400
	case 38400: baudrate = B38400; break;
#endif
#ifdef B57600
	case 57600: baudrate = B57600; break;
#endif
#ifdef B115200
	case 115200: baudrate = B115200; break;
#endif
#ifdef B230400
	case 230400: baudrate = B230400; break;
#endif
#ifdef B460800
	case 460800: baudrate = B460800; break;
#endif
#ifdef B500000
	case 500000: baudrate = B500000; break;
#endif
#ifdef B576000
	case 576000: baudrate = B576000; break;
#endif
#ifdef B921600
	case 921600: baudrate = B921600; break;
#endif
#ifdef B1000000
	case 1000000: baudrate = B1000000; break;
#endif
#ifdef B1152000
	case 1152000: baudrate = B1152000; break;
#endif
#ifdef B1500000
	case 1500000: baudrate = B1500000; break;
#endif
#ifdef B2000000
	case 2000000: baudrate = B2000000; break;
#endif
#ifdef B2500000
	case 2500000: baudrate = B2500000; break;
#endif
#ifdef B3000000
	case 3000000: baudrate = B3000000; break;
#endif
#ifdef B3500000
	case 3500000: baudrate = B3500000; break;
#endif
#ifdef B4000000
	case 4000000: baudrate = B4000000; break;
#endif
	default:
	    fprintf(stderr, "Unknown baudrate %s, defaulting to 19200\n",
		    argv[2]);
	}
    }
    
    input_stream = open(name, O_RDWR|O_NOCTTY);
    if (input_stream == -1) {
	fprintf(stderr, "Failed to open %s", name);
	perror("");
	fprintf(stderr, "Make sure the user has permission to open device.\n");
	exit(2);
    }
    fprintf(stdout, "%s input_stream opened\n", name);
    fflush(stdout); // i should not have to do this, but file redirection did not work without it...
#ifdef __CYGWIN__
	/* For some very mysterious reason, this incantation is necessary to make
	   the serial port work under some windows machines */
	HANDLE handle = (HANDLE)get_osfhandle(input_stream);
	DCB dcb;
	if (!(GetCommState(handle, &dcb) &&
		  SetCommState(handle, &dcb))) {
		fprintf(stderr, "serial port initialisation problem\n");
		exit(2);
	}
#endif

    /* Serial port setting */
    bzero(&newtio, sizeof(newtio));
    newtio.c_cflag = CS8 | CLOCAL | CREAD;
    newtio.c_iflag = IGNPAR | IGNBRK;
    cfsetispeed(&newtio, baudrate);
    cfsetospeed(&newtio, baudrate);

    tcflush(input_stream, TCIFLUSH);
    tcsetattr(input_stream, TCSANOW, &newtio);
}

