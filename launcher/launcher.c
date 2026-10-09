/* Aura.exe: portable launcher.
 *
 * Loads the Python that ships in the "runtime" folder and runs "app\main.py".
 * Nothing is installed and the registry is not touched: everything lives in
 * this folder. If Python cannot be loaded inside this process, it is started
 * through pythonw.exe instead.
 *
 * Messages are shown in English first, then Spanish.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

#define MAXP 4096

static wchar_t g_dir[MAXP];
static wchar_t g_home[MAXP];
static wchar_t g_script[MAXP];
static wchar_t g_exe[MAXP];

static void cat(wchar_t *dst, const wchar_t *src, int cap) {
    int n = lstrlenW(dst);
    while (*src && n < cap - 1) dst[n++] = *src++;
    dst[n] = 0;
}

static int exists(const wchar_t *path) {
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

static int fail(const wchar_t *text) {
    MessageBoxW(NULL, text, L"Aura", MB_OK | MB_ICONWARNING);
    return 2;
}

/* Plan B: start pythonw.exe as a separate process. */
static int spawn(int argc, wchar_t **argv) {
    static wchar_t cmd[32768];
    wchar_t py[MAXP];
    int i;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    py[0] = 0; cat(py, g_home, MAXP); cat(py, L"\\pythonw.exe", MAXP);
    if (!exists(py))
        return fail(L"Aura couldn't start: runtime\\pythonw.exe is missing.\n\n"
                    L"No se pudo iniciar Aura: falta runtime\\pythonw.exe.");
    cmd[0] = 0;
    cat(cmd, L"\"", 32768); cat(cmd, py, 32768); cat(cmd, L"\" -I \"", 32768);
    cat(cmd, g_script, 32768); cat(cmd, L"\"", 32768);
    for (i = 1; i < argc; i++) {
        cat(cmd, L" \"", 32768); cat(cmd, argv[i], 32768); cat(cmd, L"\"", 32768);
    }
    ZeroMemory(&si, sizeof(si)); si.cb = sizeof(si);
    if (!CreateProcessW(py, cmd, NULL, NULL, FALSE, 0, NULL, g_dir, &si, &pi))
        return fail(L"Aura couldn't start.\n\nNo se pudo iniciar Aura.");
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

typedef int (*py_main_t)(int, wchar_t **);
typedef void (*py_sethome_t)(const wchar_t *);

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR unused, int show) {
    wchar_t dll[MAXP];
    wchar_t **argv;
    wchar_t **pyargv;
    int argc = 0, i, n;
    HMODULE py;
    py_main_t py_main;
    py_sethome_t py_sethome;
    (void)inst; (void)prev; (void)unused; (void)show;

    n = (int)GetModuleFileNameW(NULL, g_exe, MAXP);
    if (n <= 0 || n >= MAXP - 1)
        return fail(L"The path to Aura's folder is too long.\n\n"
                    L"La ruta de la carpeta de Aura es demasiado larga.");
    lstrcpynW(g_dir, g_exe, MAXP);
    for (i = lstrlenW(g_dir) - 1; i >= 0 && g_dir[i] != L'\\' && g_dir[i] != L'/'; i--) {}
    if (i < 0)
        return fail(L"Couldn't locate Aura's folder.\n\nNo se pudo ubicar la carpeta de Aura.");
    g_dir[i] = 0;

    g_home[0] = 0;   cat(g_home, g_dir, MAXP);   cat(g_home, L"\\runtime", MAXP);
    g_script[0] = 0; cat(g_script, g_dir, MAXP); cat(g_script, L"\\app\\main.py", MAXP);
    dll[0] = 0;      cat(dll, g_home, MAXP);     cat(dll, L"\\python312.dll", MAXP);

    if (!exists(dll) || !exists(g_script))
        return fail(L"Aura needs the \"runtime\" and \"app\" folders that come with this file.\n"
                    L"If you opened it from inside the .zip, extract the whole folder first "
                    L"(right-click the .zip, \"Extract All\") and run Aura.exe from there.\n\n"
                    L"Aura necesita las carpetas \"runtime\" y \"app\" que vienen junto con este archivo.\n"
                    L"Si lo abriste desde adentro del .zip, primero extraé toda la carpeta "
                    L"(clic derecho sobre el .zip, \"Extraer todo\") y abrí Aura.exe desde ahí.");

    argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv == NULL) argc = 0;

    py = LoadLibraryExW(dll, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    py_main = py ? (py_main_t)(void *)GetProcAddress(py, "Py_Main") : NULL;
    py_sethome = py ? (py_sethome_t)(void *)GetProcAddress(py, "Py_SetPythonHome") : NULL;
    if (py_main == NULL || py_sethome == NULL)
        return spawn(argc, argv);

    pyargv = (wchar_t **)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(wchar_t *) * (size_t)(argc + 4));
    if (pyargv == NULL) return spawn(argc, argv);
    n = 0;
    pyargv[n++] = g_exe;
    pyargv[n++] = L"-I";           /* isolated: ignores PYTHON* variables and user packages */
    pyargv[n++] = g_script;
    for (i = 1; i < argc; i++) pyargv[n++] = argv[i];
    pyargv[n] = NULL;

    SetCurrentDirectoryW(g_dir);
    py_sethome(g_home);
    return py_main(n, pyargv);
}
