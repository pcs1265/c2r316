; C→R316 런타임 코어 - 하드웨어 프리미티브
; C로 표현할 수 없는 최소한의 어셈블리만 포함:
;   - 터미널 초기화 (__term_init) : TPTASM %eval/%define 매크로 필요
;   - putchar / getchar           : 메모리 맵드 I/O 직접 접근
;   - __udiv / __umod             : / 연산자 자체가 이 함수를 호출하므로
;                                   C로 구현하면 무한 재귀 발생
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
; TPTASM %eval/%define 매크로를 사용하므로 C로 작성 불가
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
; 메모리 맵드 I/O 직접 접근 → C로 작성 불가
; 입력: r1 = 문자 코드 / 출력: r1 = 출력한 문자
putchar:
    st r1, _term_term
    jmp r31

; ── getchar() → int ──────────────────────────────────────────────────────────
; 메모리 맵드 I/O 폴링 루프 → C로 작성 불가
; 입력: 없음 / 출력: r1 = 키 코드 (0이 아닐 때까지 대기)
getchar:
    ld r1, _term_input
    test r1, r1
    jz getchar
    jmp r31

; ── __udiv: 부호 없는 16비트 나눗셈 ─────────────────────────────────────────
; C의 / 연산자가 이 함수를 호출하므로, C로 구현하면 무한 재귀 발생
; 입력: r1 = 피제수, r2 = 제수
; 출력: r1 = 몫, r2 = 나머지
__udiv:
    mov r3, 0              ; 몫
.__udiv_loop:
    sub r0, r1, r2         ; flags only (r1 - r2)
    jl .__udiv_done        ; r1 < r2이면 종료
    sub r1, r2
    add r3, 1
    jmp .__udiv_loop
.__udiv_done:
    mov r2, r1             ; 나머지
    mov r1, r3             ; 몫
    jmp r31

; ── __umod: 부호 없는 16비트 나머지 ─────────────────────────────────────────
; __udiv와 동일한 이유로 어셈블리로 유지
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
