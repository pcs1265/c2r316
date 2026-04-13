; C→R316 런타임 라이브러리
; 컴파일러 출력 파일의 끝에 %include "runtime.asm" 으로 포함됨
;
; ABI:
;   r1..r4  : 인자 / 반환값
;   r5..r13 : caller-saved 임시
;   r14..r29: callee-saved
;   r30 (sp): 스택 포인터
;   r31 (lr): 링크 레지스터
;
; 터미널 주소 (demo.asm 규격):
;   0x9F80 : term_input  (키보드 읽기)
;   0x9F84 : term_raw    (raw 출력 - scrollprint)
;   0x9F85 : term_single (단일 문자 출력)
;   0x9FB5 : term_term   (일반 문자 출력 - 개행 처리)
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

; ── 터미널 초기화 ─────────────────────────────────────────────────────────────
; 입력: 없음 / 출력: 없음 / 파괴: r1
__term_init:
    st r0, _term_input
    mov r1, { _term_width 1 - }
    shl r1, 5
    st r1, _term_hrange
    mov r1, { _term_height 1 - }
    shl r1, 5
    st r1, _term_vrange
    mov r1, 0x0A           ; 녹색 on 검정
    st r1, _term_colour
    mov r1, _nlchar
    st r1, _term_nlchar
    ; 화면 전체 공백으로 클리어
    mov r1, ' '
    mov r2, 0
.__term_init_clear:
    st r1, _term_raw
    add r2, 1
    cmp r2, _term_height
    jne .__term_init_clear
    jmp r31

; ── putchar(int c) ────────────────────────────────────────────────────────────
; 입력: r1 = 문자 코드 / 출력: r1 = 출력한 문자
putchar:
    st r1, _term_term
    jmp r31

; ── getchar() → int ──────────────────────────────────────────────────────────
; 입력: 없음 / 출력: r1 = 키 코드 (0이 아닐 때까지 대기)
getchar:
    ld r1, _term_input
    test r1, r1
    jz getchar
    jmp r31

; ── puts(char *s) ─────────────────────────────────────────────────────────────
; 입력: r1 = 문자열 포인터 (null 종료) / 출력: 없음
puts:
    st r31, r30, 0xFFFF    ; lr 저장 (sp-1)
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
; puts와 동일하나 개행 없음
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
; 입력: r1 = 부호 있는 16비트 정수 / 출력: 없음
print_int:
    st r31, r30, 0xFFFF
    sub r30, 1
    ; 음수 처리
    test r1, 0x8000
    jz .__pi_pos
    mov r2, '-'
    st r2, _term_term
    sub r1, r0, r1         ; negate: r0 ALU-wise=0, so r1 = -r1
.__pi_pos:
    ; r1이 0이면 특수 처리
    test r1, r1
    jnz .__pi_nonzero
    mov r2, '0'
    st r2, _term_term
    jmp .__pi_done
.__pi_nonzero:
    ; 스택에 숫자를 역순으로 push
    mov r3, 0              ; 자릿수 카운트
.__pi_digit_loop:
    test r1, r1
    jz .__pi_print_loop
    ; r1 % 10 → r2, r1 / 10 → r1
    mov r4, r1
    mulh r5, r4, 6554      ; floor(r4/10) for r4 in [0,65535]
    mul r6, r5, 10
    sub r2, r4, r6         ; 나머지
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
; 입력: r1 = 부호 없는 16비트 정수
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
; 입력: r1 = 값 (16비트), 4자리 16진수로 출력
print_hex:
    mov r2, 4              ; 4 니블
.__ph_loop:
    sub r2, 1
    ; r1의 최상위 니블 추출
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

; ── __udiv: 부호 없는 16비트 나눗셈 ─────────────────────────────────────────
; 입력: r1 = 피제수, r2 = 제수
; 출력: r1 = 몫, r2 = 나머지
__udiv:
    ; 간단한 반복 빼기 방식 (느리지만 정확)
    ; TODO: 빠른 알고리즘으로 교체
    mov r3, 0              ; 몫
.__udiv_loop:
    ; r1 >= r2 이면 빼기
    sub r0, r1, r2         ; flags only
    jl .__udiv_done        ; r1 < r2 (signed, but values are unsigned 0..65535)
    sub r1, r2
    add r3, 1
    jmp .__udiv_loop
.__udiv_done:
    mov r2, r1             ; 나머지
    mov r1, r3             ; 몫
    jmp r31

; ── __umod: 부호 없는 16비트 나머지 ─────────────────────────────────────────
; 입력: r1 = 피제수, r2 = 제수
; 출력: r1 = 나머지
__umod:
    st r31, r30, 0xFFFF
    sub r30, 1
    jmp r31, __udiv
    mov r1, r2             ; 나머지를 r1에
    add r30, 1
    ld r31, r30, 0xFFFF
    jmp r31

; ── memset(void *dst, int val, int n) ────────────────────────────────────────
; 입력: r1=dst, r2=val, r3=n
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
; 입력: r1=dst, r2=src, r3=n
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
; 입력: r1 = 문자열 포인터 / 출력: r1 = 길이
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
; 출력: r1 = 0(같음), 양수(a>b), 음수(a<b)
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
