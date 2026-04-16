; C->R316 Runtime Core - Hardware Primitives
; Contains only the minimal assembly that cannot be expressed in C:
;   - Terminal init (__term_init) : requires TPTASM %eval/%define macros
;   - putchar / getchar           : direct memory-mapped I/O access
;   - __udiv / __umod             : the / operator itself calls these,
;                                   so a C implementation would recurse infinitely
;
; ABI:
;   r1..r4  : arguments / return value
;   r5..r13 : caller-saved temporaries
;   r14..r29: callee-saved
;   r30 (sp): stack pointer
;   r31 (lr): link register
;
; Terminal addresses (demo.asm spec):
;   0x9F80 : term_input  (keyboard read)
;   0x9F84 : term_raw    (raw output - scrollprint)
;   0x9F85 : term_single (single character output)
;   0x9FB5 : term_term   (normal character output - handles newline)
;   0x9FC2 : term_hrange
;   0x9FC3 : term_vrange
;   0x9FC4 : term_cursor
;   0x9FC5 : term_nlchar
;   0x9FC6 : term_colour

%eval _term_base   0x9F80
%eval _term_input  _term_base 0x00 +
%eval _term_raw    _term_base 0x04 +
%eval _term_single _term_base 0x05 +
%eval _term_term   _term_base 0x35 +
%eval _term_hrange _term_base 0x42 +
%eval _term_vrange _term_base 0x43 +
%eval _term_cursor _term_base 0x44 +
%eval _term_nlchar _term_base 0x45 +
%eval _term_colour _term_base 0x46 +

%define _term_width  12
%define _term_height 8
%define _nlchar      10

; -- __term_init ------------------------------------------------------------------
; Requires TPTASM %eval/%define macros, cannot be written in C
; Input: none / Output: none / Clobbers: r1
__term_init:
    st r0, _term_input
    mov r1, { _term_width 1 - }
    shl r1, 5
    st r1, _term_hrange
    mov r1, { _term_height 1 - }
    shl r1, 5
    st r1, _term_vrange
    mov r1, 0x0A           ; green on black
    st r1, _term_colour
    mov r1, _nlchar
    st r1, _term_nlchar
    ; clear screen with spaces
    mov r1, ' '
    mov r2, 0
.__term_init_clear:
    st r1, _term_raw
    add r2, 1
    cmp r2, _term_height
    jne .__term_init_clear
    jmp r31

; -- putchar(int c) ---------------------------------------------------------------
; Direct memory-mapped I/O, cannot be written in C
; Input: r1 = character code / Output: r1 = character written
putchar:
    st r1, _term_term
    jmp r31

; -- getchar() -> int -------------------------------------------------------------
; Memory-mapped I/O polling loop, cannot be written in C
; Input: none / Output: r1 = key code (waits until non-zero)
getchar:
    ld r1, _term_input
    test r1, r1
    jz getchar
    jmp r31

; -- __udiv: unsigned 16-bit division ---------------------------------------------
; The C / operator calls this function, so a C implementation would recurse infinitely
; Input: r1 = dividend, r2 = divisor
; Output: r1 = quotient, r2 = remainder
__udiv:
    mov r3, 0              ; quotient
.__udiv_loop:
    sub r0, r1, r2         ; flags only (r1 - r2)
    jl .__udiv_done        ; r1 < r2, done
    sub r1, r2
    add r3, 1
    jmp .__udiv_loop
.__udiv_done:
    mov r2, r1             ; remainder
    mov r1, r3             ; quotient
    jmp r31

; -- __umod: unsigned 16-bit remainder --------------------------------------------
; Kept in assembly for the same reason as __udiv
; Input: r1 = dividend, r2 = divisor
; Output: r1 = remainder
__umod:
    sub r30, 1
    st r31, r30, 0
    jmp r31, __udiv
    mov r1, r2
    ld r31, r30, 0
    add r30, 1
    jmp r31

; -- __sdiv: signed 16-bit division (C standard: truncate toward zero) ------------
; Input: r1 = dividend (signed), r2 = divisor (signed)
; Output: r1 = quotient, r2 = remainder
__sdiv:
    sub r30, 3
    st r31, r30, 2          ; save LR
    st r0, r30, 0           ; q_neg = 0  (is quotient negative?)
    st r0, r30, 1           ; r_neg = 0  (is remainder negative? same sign as dividend)
    ; if dividend is negative, convert to absolute value
    sub r0, r1, r0          ; flags = r1 - 0 (r0 is always 0)
    jnl .__sdiv_d_pos
    sub r1, r0, r1          ; r1 = -r1
    mov r3, 1
    st r3, r30, 0           ; q_neg = 1
    st r3, r30, 1           ; r_neg = 1
.__sdiv_d_pos:
    ; if divisor is negative, convert to absolute value
    sub r0, r2, r0          ; flags = r2 - 0
    jnl .__sdiv_v_pos
    sub r2, r0, r2          ; r2 = -r2
    ld r3, r30, 0
    xor r3, 1
    st r3, r30, 0           ; q_neg ^= 1
.__sdiv_v_pos:
    jmp r31, __udiv         ; r1 = |a|/|b|, r2 = |a|%|b|
    ; apply sign to quotient
    ld r3, r30, 0
    test r3, r3
    jz .__sdiv_q_ok
    sub r1, r0, r1          ; r1 = -r1
.__sdiv_q_ok:
    ; apply sign to remainder (same sign as dividend)
    ld r3, r30, 1
    test r3, r3
    jz .__sdiv_done
    sub r2, r0, r2          ; r2 = -r2
.__sdiv_done:
    ld r31, r30, 2
    add r30, 3
    jmp r31

; -- __smod: signed 16-bit remainder ----------------------------------------------
; Input: r1 = dividend, r2 = divisor / Output: r1 = remainder
__smod:
    sub r30, 1
    st r31, r30, 0
    jmp r31, __sdiv
    mov r1, r2
    ld r31, r30, 0
    add r30, 1
    jmp r31
