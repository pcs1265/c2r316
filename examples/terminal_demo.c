/*
 * terminal_demo.c — showcase of terminal.h features
 *
 * Demonstrates:
 *   - TERM_* colour constants
 *   - term_set_color(fg, bg)  : foreground/background colour
 *   - term_move(col, row)     : cursor positioning
 *   - term_putch / puts       : character output
 *   - term_getch / scanf      : line-buffered input with echo + backspace
 *
 * Terminal: 24 cols x 16 rows, 16 colours (CGA palette).
 */

#include <terminal.h>
#include <stdio.h>

/* ── helpers ────────────────────────────────────────────────────────────── */

static void print_str_at(int col, int row, int fg, int bg, char *s) {
    term_move(col, row);
    term_set_color(fg, bg);
    print_str(s);
}

static void hline(int col, int row, int fg, int bg, int ch, int len) {
    int i;
    term_move(col, row);
    term_set_color(fg, bg);
    i = 0;
    while (i < len) {
        term_putch(ch);
        i++;
    }
}

/* ── demo sections ──────────────────────────────────────────────────────── */

static void draw_header(void) {
    hline(0, 0, TERM_BLACK, TERM_LCYAN, ' ', 24);
    print_str_at(2, 0, TERM_BLACK, TERM_LCYAN, "R316 TERMINAL DEMO");
}

static void draw_palette(void) {
    int i;
    print_str_at(0, 2, TERM_LGREY, TERM_BLACK, "Colours:");

    /* colours 0-7 */
    i = 0;
    while (i < 8) {
        term_move(i * 3, 3);
        term_set_color(TERM_WHITE, i);
        term_putch(' ');
        term_putch('0' + i);
        term_putch(' ');
        i++;
    }

    /* colours 8-15 */
    i = 0;
    while (i < 8) {
        term_move(i * 3, 4);
        term_set_color(TERM_BLACK, i + 8);
        term_putch(' ');
        term_putch('0' + i);   /* 0-7 labels for 8-15 */
        term_putch(' ');
        i++;
    }
}

static void draw_cursor_demo(void) {
    print_str_at(0, 6, TERM_LYELLOW, TERM_BLACK, "Cursor positions:");
    print_str_at(0,  7, TERM_LRED,     TERM_BLACK, "(0,7)");
    print_str_at(9,  7, TERM_LGREEN,   TERM_BLACK, "(9,7)");
    print_str_at(18, 7, TERM_LBLUE,    TERM_BLACK, "(18,7)");
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
        term_set_color(colours[i], TERM_BLACK);
        term_putch(msg[i]);
        i++;
    }
}

static void do_input(void) {
    char name[16];

    print_str_at(0, 11, TERM_LGREY, TERM_BLACK, "Your name: ");
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

/* ── main ───────────────────────────────────────────────────────────────── */

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
