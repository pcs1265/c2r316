/* test_terminal.c — verify terminal.h cursor and colour API */

#include <terminal.h>
#include <stdio.h>

static int pass_count;
static int fail_count;

static void check(char *name, int got, int expected) {
    if (got == expected) {
        puts("PASS");
        pass_count++;
    } else {
        puts("FAIL");
        fail_count++;
    }
}

int main(void) {
    int c1; int r1;
    int c2; int r2;
    int c3; int r3;
    int c4; int r4;
    int c5; int r5;

    puts("=== test_terminal ===");

    /* snapshot state after each operation before any output changes it */

    _cursor_col = 0;
    _cursor_row = 0;
    term_putch('A');
    c1 = _cursor_col; r1 = _cursor_row;     /* expect col=1 row=0 */

    term_putch('\n');
    c2 = _cursor_col; r2 = _cursor_row;     /* expect col=0 row=1 */

    term_move(3, 5);
    c3 = _cursor_col; r3 = _cursor_row;     /* expect col=3 row=5 */

    term_move(0, 0);
    term_putch('X');
    term_putch('Y');
    c4 = _cursor_col; r4 = _cursor_row;     /* expect col=2 row=0 */

    term_move(7, 2);
    c5 = _cursor_col; r5 = _cursor_row;     /* expect col=7 row=2 */

    /* output results — these calls update _cursor_row, but we already snapshotted */
    check("putch col",   c1, 1);
    check("putch row",   r1, 0);
    check("newline col", c2, 0);
    check("newline row", r2, 1);
    check("move col",    c3, 3);
    check("move row",    r3, 5);
    check("putch x2 col", c4, 2);
    check("putch x2 row", r4, 0);
    check("move2 col",   c5, 7);
    check("move2 row",   r5, 2);

    puts("================");
    print_str("PASS: "); print_int(pass_count); putchar('\n');
    print_str("FAIL: "); print_int(fail_count); putchar('\n');
    puts("=== done ===");
    return 0;
}
