; C→R316 Runtime Library
; Included at the end of compiler output via %include "runtime.asm"
;
; ABI:
;   r1..r4  : arguments / return values
;   r5..r13 : caller-saved temporaries
;   r14..r29: callee-saved
;   r30 (sp): stack pointer
;   r31 (lr): link register
;
; Terminal addresses (demo.asm spec):
;   0x9F80 : term_input  (keyboard read)
;   0x9F84 : term_raw    (raw output - scrollprint)
;   0x9F85 : term_single (single character output)
;   0x9FB5 : term_term   (general character output - handles newline)
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

%define _term_width  24
%define _term_height 16
%define _nlchar      10

; ── terminal initialization ─────────────────────────────────────────────────────────────
; in: none / out: none / clobbers: r1
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
    ; clear entire screen with spaces
    mov r1, ' '
    mov r2, 0
.__term_init_clear:
    st r1, _term_raw
    add r2, 1
    cmp r2, _term_height
    jne .__term_init_clear
    jmp r31

; ── putchar(int c) ────────────────────────────────────────────────────────────
; in: r1 = character code / out: r1 = character output
putchar:
    st r1, _term_term
    jmp r31

; ── getchar() → int ──────────────────────────────────────────────────────────
; in: none / out: r1 = key code (waits until non-zero)
getchar:
    ld r1, _term_input
    test r1, r1
    jz getchar
    jmp r31

; ── puts(char *s) ─────────────────────────────────────────────────────────────
; in: r1 = string pointer (null-terminated) / out: none
puts:
    st r31, r30, 0xFFFF    ; save lr (sp-1)
    sub r30, 1
.__puts_loop:
    ld r2, r1
    test r2, r2
    jz .__puts_done
    st r2, _term_term
    add r1, 1
    jmp .__puts_loop
.__puts_done:
    mov r2, _nlchar
    st r2, _term_term
    add r30, 1
    ld r31, r30, 0xFFFF
    jmp r31

; ── print_str(char *s) ───────────────────────────────────────────────────────
; same as puts but without trailing newline
print_str:
    ld r2, r1
    test r2, r2
    jz .__ps_done
    st r2, _term_term
    add r1, 1
    jmp print_str
.__ps_done:
    jmp r31

; ── print_int(int n) ─────────────────────────────────────────────────────────
; in: r1 = signed 16-bit integer / out: none
print_int:
    st r31, r30, 0xFFFF
    sub r30, 1
    ; handle negative
    test r1, 0x8000
    jz .__pi_pos
    mov r2, '-'
    st r2, _term_term
    sub r1, r0, r1         ; negate: r0 ALU-wise=0, so r1 = -r1
.__pi_pos:
    ; special case: r1 == 0
    test r1, r1
    jnz .__pi_nonzero
    mov r2, '0'
    st r2, _term_term
    jmp .__pi_done
.__pi_nonzero:
    ; push digits onto stack in reverse order
    mov r3, 0              ; digit count
.__pi_digit_loop:
    test r1, r1
    jz .__pi_print_loop
    ; r1 % 10 → r2, r1 / 10 → r1
    mov r4, r1
    mulh r5, r4, 6554      ; floor(r4/10) for r4 in [0,65535]
    mul r6, r5, 10
    sub r2, r4, r6         ; remainder
    add r2, '0'
    sub r30, 1
    st r2, r30             ; push digit
    add r3, 1
    mov r1, r5
    jmp .__pi_digit_loop
.__pi_print_loop:
    test r3, r3
    jz .__pi_done
    ld r2, r30
    add r30, 1
    st r2, _term_term
    sub r3, 1
    jmp .__pi_print_loop
.__pi_done:
    add r30, 1
    ld r31, r30, 0xFFFF
    jmp r31

; ── print_uint(unsigned int n) ───────────────────────────────────────────────
; in: r1 = unsigned 16-bit integer
print_uint:
    st r31, r30, 0xFFFF
    sub r30, 1
    test r1, r1
    jnz .__pu_nonzero
    mov r2, '0'
    st r2, _term_term
    jmp .__pu_done
.__pu_nonzero:
    mov r3, 0
.__pu_digit_loop:
    test r1, r1
    jz .__pu_print_loop
    mulh r5, r1, 6554
    mul r6, r5, 10
    sub r2, r1, r6
    add r2, '0'
    sub r30, 1
    st r2, r30
    add r3, 1
    mov r1, r5
    jmp .__pu_digit_loop
.__pu_print_loop:
    test r3, r3
    jz .__pu_done
    ld r2, r30
    add r30, 1
    st r2, _term_term
    sub r3, 1
    jmp .__pu_print_loop
.__pu_done:
    add r30, 1
    ld r31, r30, 0xFFFF
    jmp r31

; ── print_hex(unsigned int n) ────────────────────────────────────────────────
; in: r1 = value (16-bit), printed as 4-digit hex
print_hex:
    mov r2, 4              ; 4 nibbles
.__ph_loop:
    sub r2, 1
    ; extract top nibble of r1
    mov r3, r1
    shr r3, 12
    and r3, 0xF
    cmp 10, r3
    jbe .__ph_alpha
    add r3, '0'
    jmp .__ph_emit
.__ph_alpha:
    add r3, 55             ; 'A' - 10 = 55
.__ph_emit:
    st r3, _term_term
    shl r1, 4
    test r2, r2
    jnz .__ph_loop
    jmp r31

; ── __udiv: unsigned 16-bit division ─────────────────────────────────────────
; in: r1 = dividend, r2 = divisor
; out: r1 = quotient, r2 = remainder
__udiv:
    ; simple repeated subtraction (slow but correct)
    ; TODO: replace with faster algorithm
    mov r3, 0              ; quotient
.__udiv_loop:
    ; subtract while r1 >= r2
    sub r0, r1, r2         ; flags only
    jl .__udiv_done        ; r1 < r2 (signed, but values are unsigned 0..65535)
    sub r1, r2
    add r3, 1
    jmp .__udiv_loop
.__udiv_done:
    mov r2, r1             ; remainder
    mov r1, r3             ; quotient
    jmp r31

; ── __umod: unsigned 16-bit modulo ─────────────────────────────────────────
; in: r1 = dividend, r2 = divisor
; out: r1 = remainder
__umod:
    st r31, r30, 0xFFFF
    sub r30, 1
    jmp r31, __udiv
    mov r1, r2             ; move remainder to r1
    add r30, 1
    ld r31, r30, 0xFFFF
    jmp r31

; ── memset(void *dst, int val, int n) ────────────────────────────────────────
; in: r1=dst, r2=val, r3=n
memset:
.__ms_loop:
    test r3, r3
    jz .__ms_done
    st r2, r1
    add r1, 1
    sub r3, 1
    jmp .__ms_loop
.__ms_done:
    jmp r31

; ── memcpy(void *dst, void *src, int n) ──────────────────────────────────────
; in: r1=dst, r2=src, r3=n
memcpy:
.__mc_loop:
    test r3, r3
    jz .__mc_done
    ld r4, r2
    st r4, r1
    add r1, 1
    add r2, 1
    sub r3, 1
    jmp .__mc_loop
.__mc_done:
    jmp r31

; ── strlen(char *s) → int ────────────────────────────────────────────────────
; in: r1 = string pointer / out: r1 = length
strlen:
    mov r2, r1
.__sl_loop:
    ld r3, r2
    test r3, r3
    jz .__sl_done
    add r2, 1
    jmp .__sl_loop
.__sl_done:
    sub r1, r2, r1
    jmp r31

; ── strcmp(char *a, char *b) → int ───────────────────────────────────────────
; out: r1 = 0 (equal), positive (a>b), negative (a<b)
strcmp:
.__sc_loop:
    ld r3, r1
    ld r4, r2
    sub r5, r3, r4
    jnz .__sc_done
    test r3, r3
    jz .__sc_done
    add r1, 1
    add r2, 1
    jmp .__sc_loop
.__sc_done:
    mov r1, r5
    jmp r31

; ── __stack_init ─────────────────────────────────────────────────────────────
; Detects the top of writable RAM at runtime using binary search (6 iterations),
; sets SP (r30) to it.
; RAM size is 128..8192 words in increments of 128 (64 possible sizes = 6 bits).
; Binary search: probe the midpoint block boundary each step, converge in 6 probes.
; Uses __earlystack as a temporary stack during execution.
; Input: none / Output: none / Clobbers: r1, r2, r4, r5, r30
__stack_init:
    mov r30, __earlystack_top   ; use reserved area as temporary stack

    ; --- save return address on early stack ---
    sub r30, 1
    st  r31, r30, 0

    ; --- binary search for highest writable block (6 iterations max) ---
    ; Search over block indices lo..63; block N covers addresses N*128..(N*128+127)
    ; We probe the last word of block N: address = N*128 + 127 = N*0x80 + 0x7F
    ; lo starts at the block containing __prog_end so we never probe program memory.
    ; r1 = lo block index, r4 = hi block index, r2 = mid probe address
    mov r1, __prog_end          ; r1 = first address past program
    shr r1, 7                   ; r1 = block index of __prog_end (round down)
    mov r4, 63                  ; hi = 63
    ; if lo > hi (program fills all RAM), use block 63 as fallback
    sub r0, r4, r1
    jl  .__stack_found_fallback
.__stack_bsearch:
    add r2, r1, r4              ; r2 = lo + hi
    shr r2, 1                   ; r2 = mid block index
    shl r2, 7                   ; r2 = mid * 128
    add r2, 0x7F                ; r2 = last word of mid block
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
    ; not writable: answer is in [lo..mid-1]; hi = mid - 1
    sub r5, r2, 0x7F            ; r5 = mid * 128
    shr r5, 7                   ; r5 = mid block index
    sub r4, r5, 1               ; hi = mid - 1
    jmp .__stack_bsearch
.__stack_found_fallback:
    mov r2, 63
    shl r2, 7
    add r2, 0x7F                ; r2 = last word of block 63
.__stack_found:
    ; r2 = last word address of highest writable block = top of RAM

    ; --- set heap base and limit (limit = ram_top - 256 for stack reservation) ---
    mov r5, __prog_end
    st  r5, __heap_base
    sub r5, r2, 256
    st  r5, __heap_limit

    ; --- restore return address and set real SP ---
    ld  r31, r30, 0             ; restore saved return address from early stack
    add r30, 1
    mov r30, r2
    add r30, 1                  ; SP = ram_top + 1 (first sub lands on ram_top)
    jmp r31

; ── heap / early-stack data ──────────────────────────────────────────────────
__heap_base:  dw 0
__heap_limit: dw 0
__earlystack: dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
__earlystack_top:
__prog_end:
