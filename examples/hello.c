/* First C program running on R316 */

#include "runtime/stdio.h"

unsigned int crc16_xmodem(char* data, int length) {
    unsigned int crc = 0000; // Initial value
    while (length--) {
        crc ^= (*data++) << 8;
        for (int i = 0; i < 8; ++i) {
            if (crc & 32768)
                crc = (crc << 1) ^ 4129; // Polynomial
            else
                crc <<= 1;
        }
    }
    return crc;
}

int main() {
    char* data = "Now let me compile and test this to ensure it works on the R316 emulator:";
    printf("DATA:\n");
    for(int i = 0; i < 73; ++i){
        printf("%x ", data[i]);
    }
    printf("\n");
    printf("CRC: %x\n", crc16_xmodem(data, 73));
    return 0;
}
