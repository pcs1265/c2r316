/*
 * terminal.h -- R316 terminal MMIO layer
 *
 * Owns all direct hardware access to the terminal peripheral and the
 * state variables that go with it.  Higher-level headers (stdio.h, ...)
 * should #include <terminal.h> and call these primitives instead of
 * touching MMIO directly.
 *
 * --MMIO map (base 0x9F80) -----------------------------------------------
 *
 * Registers (offset from base):
 *   +0x42  hrange    horizontal scrollprint range (write-only)
 *   +0x43  vrange    vertical scrollprint range   (write-only)
 *   +0x44  cursor    cursor position              (write-only)
 *   +0x45  nlchar    newline trigger character    (write-only)
 *   +0x46  colour    fg/bg colour                 (write-only)
 *   +0x47  scrollmask scroll mask                 (write-only)
 *   +0x40  char0odd  custom char #0 odd columns   (write-only)
 *   +0x41  char0even custom char #0 even columns  (write-only)
 *
 * Read-only register (same address, separate from write sub-ranges):
 *   +0x00  input     keyboard input (self-clears on read)
 *
 * Scrollprint sub-range -- write to address (base + 0x00..0x3F):
 *   address bits select scrollprint mode flags:
 *     bit 5  enable newline trigger character
 *     bit 4  enable terminal mode scrolling
 *     bit 3  enable scroll mask
 *     bit 2  enable row-oriented printing
 *     bit 1  take colour from data bits [15:8]
 *     bit 0  enable terminal mode
 *   data bits: [15:12] bg index (if bit1 set), [11:8] fg index,
 *              [7:0] character index
 *   Preset addresses used by this header:
 *     +0x35 = 0b110101  nlchar+tmscroll+roworient+tmmode  -> term_putch target
 *     +0x04 = 0b000100  roworient only                    -> raw (no cursor)
 *
 * Pixel plotter sub-range -- write to address (base + 0x60..0x7F):
 *   address bits [3:0] = colour index
 *   data bits [15:8] = row, [7:0] = column  (pixel resolution = 8? block res)
 *
 * See #define blocks below for all constant and macro names.
 */

#ifndef TERMINAL_H
#define TERMINAL_H

/* --MMIO addresses ------------------------------------------------------- */
/* Change only TERM_BASE if the terminal is mapped at a different address.  */
/* All other addresses are derived from the fixed low-7-bit offsets.        */

#define TERM_BASE       0x9F80

#define TERM_INPUT      (TERM_BASE + 0x00)  /* read-only; self-clears on read */
#define TERM_RAW        (TERM_BASE + 0x04)  /* scrollprint: row-oriented, no terminal mode */
#define TERM_TERM       (TERM_BASE + 0x35)  /* scrollprint: nlchar+tmscroll+roworient+tmmode */
#define TERM_CHAR0ODD   (TERM_BASE + 0x40)
#define TERM_CHAR0EVEN  (TERM_BASE + 0x41)
#define TERM_HRANGE     (TERM_BASE + 0x42)
#define TERM_VRANGE     (TERM_BASE + 0x43)
#define TERM_CURSOR     (TERM_BASE + 0x44)
#define TERM_NLCHAR     (TERM_BASE + 0x45)
#define TERM_COLOUR     (TERM_BASE + 0x46)
#define TERM_SCROLLMASK (TERM_BASE + 0x47)
#define TERM_PLOTPIX_BASE (TERM_BASE + 0x60)  /* + colour index in low 4 bits of addr */

/* TERM_TERM_COL: scrollprint with colour embedded in data (addr bit1=1).   */
/* Use this to set fg/bg and print a character atomically in one write,      */
/* avoiding frame-timing issues when changing colour per character.          */
/* data = (bg<<12)|(fg<<8)|char  -> write to TERM_TERM_COL                  */
#define TERM_TERM_COL   (TERM_BASE + 0x37)

/* --Register encoding ---------------------------------------------------- */

/* cursor register: bits[9:5]=row, bits[4:0]=col */
#define TERM_CURSOR_VAL(col, row)  (((row) << 5) | (col))

/* hrange / vrange: bits[9:5]=high index, bits[4:0]=low index */
#define TERM_RANGE_VAL(lo, hi)     (((hi) << 5) | (lo))

/* colour register: bits[7:4]=bg, bits[3:0]=fg */
#define TERM_COLOUR_VAL(fg, bg)    (((bg) << 4) | (fg))

/* plotpix: MMIO address encodes colour; data encodes pixel position */
#define TERM_PLOTPIX_ADDR(colour)  (TERM_PLOTPIX_BASE | ((colour) & 0xF))
#define TERM_PLOTPIX_VAL(col, row) (((row) << 8) | (col))

/* --Colour indices ------------------------------------------------------- */

#define TERM_BLACK    0   /* #000000 */
#define TERM_DBLUE    1   /* #0000AA */
#define TERM_DGREEN   2   /* #00AA00 */
#define TERM_DCYAN    3   /* #00AAAA */
#define TERM_DRED     4   /* #AA0000 */
#define TERM_DMAGENTA 5   /* #AA00AA */
#define TERM_DYELLOW  6   /* #AAAA00 */
#define TERM_LGREY    7   /* #AAAAAA */
#define TERM_DGREY    8   /* #555555 */
#define TERM_LBLUE    9   /* #5555FF */
#define TERM_LGREEN   10  /* #55FF55 */
#define TERM_LCYAN    11  /* #55FFFF */
#define TERM_LRED     12  /* #FF5555 */
#define TERM_LMAGENTA 13  /* #FF55FF */
#define TERM_LYELLOW  14  /* #FFFF55 */
#define TERM_WHITE    15  /* #FFFFFF */

/* --Terminal state ------------------------------------------------------- */

static int _cursor_col;
static int _cursor_row;

/* line-input buffer -- filled one line at a time, drained char by char */
#define _IBUF_SIZE 64
static char _ibuf[_IBUF_SIZE];
static int  _ibuf_len;
static int  _ibuf_pos;

/* --Output --------------------------------------------------------------- */

__attribute__((always_inline)) static void term_putch(int c) {
    asm("st %0, %1" : "r"(c), "r"(TERM_TERM));
    if (c == '\n') {
        _cursor_col = 0;
        _cursor_row++;
    } else {
        _cursor_col++;
    }
}

/* Colour and character packed into one atomic scrollprint write.           */
/* Avoids frame-timing issues when changing colour per character.           */
static void term_putch_col(int c, int fg, int bg) {
    int *addr;
    int data;
    addr = TERM_TERM_COL;
    data = (bg << 12) | (fg << 8) | (c & 0xFF);
    *addr = data;
    if (c == '\n') {
        _cursor_col = 0;
        _cursor_row++;
    } else {
        _cursor_col++;
    }
}

/* --Cursor --------------------------------------------------------------- */

static void term_move(int col, int row) {
    int *cur;
    int pos;
    cur = TERM_CURSOR;
    pos = TERM_CURSOR_VAL(col, row);
    *cur = pos;
    _cursor_col = col;
    _cursor_row = row;
}

/* --Colour --------------------------------------------------------------- */

static void term_set_color(int fg, int bg) {
    int *col;
    col = TERM_COLOUR;
    *col = TERM_COLOUR_VAL(fg, bg);
}

/* --Input ---------------------------------------------------------------- */

static int term_getch(void) {
    int *port;
    int c;

    if (_ibuf_pos < _ibuf_len) {
        c = _ibuf[_ibuf_pos];
        _ibuf_pos++;
        return c;
    }

    /* buffer empty -- read a new line with echo and backspace support */
    _ibuf_len = 0;
    _ibuf_pos = 0;
    port = TERM_INPUT;
    while (1) {
        /* input register self-clears on read; 0 means no key pressed */
        c = *port;
        while (c == 0) c = *port;

        if (c == 8 || c == 127) {           /* backspace / DEL */
            if (_ibuf_len > 0) {
                _ibuf_len--;
                if (_cursor_col > 0) {
                    term_move(_cursor_col - 1, _cursor_row);
                    term_putch(' ');
                    term_move(_cursor_col - 1, _cursor_row);
                }
            }
        } else if (c == '\r' || c == '\n') {
            term_putch('\n');
            if (_ibuf_len < _IBUF_SIZE - 1) {
                _ibuf[_ibuf_len] = '\n';
                _ibuf_len++;
            }
            break;
        } else {
            if (_ibuf_len < _IBUF_SIZE - 1) {
                term_putch(c);
                _ibuf[_ibuf_len] = c;
                _ibuf_len++;
            }
        }
    }

    c = _ibuf[_ibuf_pos];
    _ibuf_pos++;
    return c;
}

#endif /* TERMINAL_H */
