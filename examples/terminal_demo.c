/*
 * terminal_demo.c -- showcase of terminal.h features
 *
 * Demonstrates:
 *   - TERM_* colour constants
 *   - term_set_color(fg, bg)      : foreground/background colour
 *   - term_putch_col(c, fg, bg)   : atomic per-character colour
 *   - term_move(col, row)         : cursor positioning
 *   - term_putch / puts           : character output
 *   - term_getch / scanf          : line-buffered input with echo + backspace
 *
 * Terminal: 24 cols x 16 rows, 16 colours (CGA palette).
 */

#include <terminal.h>
#include <stdio.h>

static void draw_header(void) {
    term_move(2, 0);
    term_set_color(TERM_LCYAN, TERM_BLACK);
    print_str("R316 TERMINAL DEMO");
}

static void draw_palette(void) {
    int i;

    term_move(0, 2);
    term_set_color(TERM_LGREY, TERM_BLACK);
    print_str("Colours:");

    i = 0;
    while (i < 8) {
        term_move(i * 3, 3);
        term_putch_col(' ',     TERM_WHITE, i);
        term_putch_col('0' + i, TERM_WHITE, i);
        term_putch_col(' ',     TERM_WHITE, i);
        i++;
    }

    i = 0;
    while (i < 8) {
        term_move(i * 3, 4);
        term_putch_col(' ',     TERM_BLACK, i + 8);
        term_putch_col('0' + i, TERM_BLACK, i + 8);
        term_putch_col(' ',     TERM_BLACK, i + 8);
        i++;
    }
}

static void draw_cursor_demo(void) {
    term_move(0, 6);
    term_set_color(TERM_LYELLOW, TERM_BLACK);
    print_str("Cursor positions:");

    term_move(0,  7); term_set_color(TERM_LRED,     TERM_BLACK); print_str("(0,7)");
    term_move(9,  7); term_set_color(TERM_LGREEN,   TERM_BLACK); print_str("(9,7)");
    term_move(18, 7); term_set_color(TERM_LBLUE,    TERM_BLACK); print_str("(18,7)");
}

static void draw_rainbow(void) {
    int colours[7];
    int i;
    char *msg;

    colours[0] = TERM_LRED;
    colours[1] = TERM_LYELLOW;
    colours[2] = TERM_LGREEN;
    colours[3] = TERM_LCYAN;
    colours[4] = TERM_LBLUE;
    colours[5] = TERM_LMAGENTA;
    colours[6] = TERM_WHITE;

    msg = "RAINBOW";
    term_move(8, 9);
    i = 0;
    while (msg[i]) {
        term_putch_col(msg[i], colours[i], TERM_BLACK);
        i++;
    }
}

static void do_input(void) {
    char name[16];

    term_move(0, 11);
    term_set_color(TERM_LGREY, TERM_BLACK);
    print_str("Your name: ");
    term_set_color(TERM_WHITE, TERM_BLACK);
    scanf("%s", name);

    term_move(0, 13);
    term_set_color(TERM_LGREEN, TERM_BLACK);
    print_str("Hello, ");
    term_set_color(TERM_LYELLOW, TERM_BLACK);
    print_str(name);
    term_set_color(TERM_LGREEN, TERM_BLACK);
    term_putch('!');
}

int main(void) {
    term_set_color(TERM_LGREEN, TERM_BLACK);

    draw_header();
    draw_palette();
    draw_cursor_demo();
    draw_rainbow();
    do_input();

    term_move(0, 15);
    term_set_color(TERM_LGREY, TERM_BLACK);
    return 0;
}
