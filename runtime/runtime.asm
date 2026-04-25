; C→R316 Runtime — bootstrap and compiler-internal helpers only.
;
; ABI (see docs/ABI.md for full specification):
;   r0       : zero (read-only)
;   r1..r6   : arguments / return values (a0-a5)
;   r7..r18  : caller-saved temporaries (t0-t11)
;   r19..r29 : callee-saved (s0-s10)
;   r30 (sp) : stack pointer
;   r31 (lr) : link register
;
; Terminal addresses:
;   0x9F80 : term_input   (keyboard read)
;   0x9F84 : term_raw     (raw scrollprint)
;   0x9FB5 : term_term    (character output, handles newline)
;   0x9FC2 : term_hrange
;   0x9FC3 : term_vrange
;   0x9FC5 : term_nlchar
;   0x9FC6 : term_colour

%eval _term_base   0x9F80
%eval _term_input  _term_base 0x00 +
%eval _term_raw    _term_base 0x04 +
%eval _term_term   _term_base 0x35 +
%eval _term_hrange _term_base 0x42 +
%eval _term_vrange _term_base 0x43 +
%eval _term_cursor _term_base 0x44 +
%eval _term_nlchar _term_base 0x45 +
%eval _term_colour _term_base 0x46 +

%define _term_width  24
%define _term_height 16
%define _nlchar      10

; ── entry point ──────────────────────────────────────────────────────────────
start:
    jmp r31, __stack_init
    jmp r31, __term_init
    jmp r31, _C_main
    hlt

; ── __term_init ──────────────────────────────────────────────────────────────
; Configure terminal geometry, colour, and newline character; clear screen.
; in: none / out: none / clobbers: r1, r2
__term_init:
    st r0, _term_input
    mov r1, { _term_width 1 - }
    shl r1, 5
    st r1, _term_hrange
    mov r1, { _term_height 1 - }
    shl r1, 5
    st r1, _term_vrange
    mov r1, 0x0A                ; green on black
    st r1, _term_colour
    mov r1, _nlchar
    st r1, _term_nlchar
    st r0, _term_cursor
    mov r1, ' '
    mov r2, 0
.__term_init_clear:
    st r1, _term_raw
    add r2, 1
    cmp r2, _term_height
    jne .__term_init_clear
    jmp r31

; ── __stack_init ─────────────────────────────────────────────────────────────
; Detect top of writable RAM via binary search; initialise SP and heap bounds.
; RAM size: 128..8192 words in 128-word blocks (64 possibilities = 6 iterations).
; in: none / out: none / clobbers: r1, r2, r4, r5, r30
__stack_init:
    mov r30, __earlystack_top

    sub r30, 1
    st  r31, r30, 0

    mov r1, __prog_end
    shr r1, 7
    mov r4, 63
    sub r0, r4, r1
    jl  .__stack_found_fallback
.__stack_bsearch:
    add r2, r1, r4
    shr r2, 1
    shl r2, 7
    add r2, 0x7F
    mov r5, 0x1234
    st  r5, r2
    ld  r5, r2
    cmp r5, 0x1234
    jnz .__stack_not_writable
    sub r5, r2, 0x7F
    shr r5, 7
    cmp r1, r4
    jz  .__stack_found
    add r1, r5, 1
    jmp .__stack_bsearch
.__stack_not_writable:
    sub r5, r2, 0x7F
    shr r5, 7
    sub r4, r5, 1
    jmp .__stack_bsearch
.__stack_found_fallback:
    mov r2, 63
    shl r2, 7
    add r2, 0x7F
.__stack_found:
    mov r5, __prog_end
    st  r5, __heap_base
    sub r5, r2, 256
    st  r5, __heap_limit

    ld  r31, r30, 0
    add r30, 1
    mov r30, r2
    add r30, 1
    jmp r31

; ── __udiv(r1=dividend, r2=divisor) → r1=quotient ────────────────────────────
__udiv:
    mov r10, 0
    mov r11, 16
.__udiv_loop:
    add r1, r1
    adc r10, r10
    sub r12, r10, r2
    jc  .__udiv_skip
    mov r10, r12
    or  r1, 1
.__udiv_skip:
    sub r11, 1
    jnz .__udiv_loop
    jmp r31

; ── __umod(r1=dividend, r2=divisor) → r1=remainder ───────────────────────────
__umod:
    mov r10, 0
    mov r11, 16
.__umod_loop:
    add r1, r1
    adc r10, r10
    sub r12, r10, r2
    jc  .__umod_skip
    mov r10, r12
.__umod_skip:
    sub r11, 1
    jnz .__umod_loop
    mov r1, r10
    jmp r31

; ── data ─────────────────────────────────────────────────────────────────────
__heap_base:  dw 0
__heap_limit: dw 0
__earlystack: dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
__earlystack_top:
__prog_end:
