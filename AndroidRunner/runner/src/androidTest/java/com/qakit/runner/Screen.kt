package com.qakit.runner

import android.accessibilityservice.AccessibilityServiceInfo
import android.app.UiAutomation
import android.graphics.Bitmap
import android.graphics.Point
import android.graphics.Rect
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiSelector
import java.io.ByteArrayOutputStream
import java.security.MessageDigest

/**
 * 화면 읽기·조작. 접근성 API로 창(window)들을 직접 읽는다 (uiautomator dump보다 빠르다).
 *
 * 타입 규칙은 qakit lib/qakit/15_android.py의 android_type과 같아야 한다 (덤프 텍스트는 호스트가 그 코드로 만든다).
 */
class Screen(val pkg: String) {
    val instrumentation = InstrumentationRegistry.getInstrumentation()
    val device: UiDevice = UiDevice.getInstance(instrumentation)
    val ua: UiAutomation = instrumentation.uiAutomation

    init {
        // 모든 창(팝업·드롭다운·시스템 대화상자)과, 접근성에 중요하지 않은 뷰(id만 있는 칸)까지 본다
        val info = ua.serviceInfo
        info.flags = info.flags or AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
            AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS or AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
        ua.serviceInfo = info
    }

    val density: Float get() = instrumentation.targetContext.resources.displayMetrics.density

    val screenRect: Rect
        get() = Rect(0, 0, device.displayWidth, device.displayHeight)

    // ───────────────────────────── 트리 ─────────────────────────────

    class Node(val info: AccessibilityNodeInfo, val parent: Node?, val window: Win) {
        val children = mutableListOf<Node>()
        val cls: String = info.className?.toString() ?: ""
        val text: String = info.text?.toString() ?: ""
        val desc: String = info.contentDescription?.toString() ?: ""
        val hint: String = if (android.os.Build.VERSION.SDK_INT >= 26) info.hintText?.toString() ?: "" else ""
        val resourceId: String = info.viewIdResourceName ?: ""
        val id: String = shortId(resourceId)
        val bounds = Rect().also { info.getBoundsInScreen(it) }
        val clickable = info.isClickable
        val enabled = info.isEnabled
        val selected = info.isSelected || info.isChecked
        val visibleToUser = info.isVisibleToUser
        val editable = info.isEditable
        lateinit var type: String
        val label: String get() = (text.ifEmpty { desc }).replace("\n", " ")

        fun descendants(): Sequence<Node> = sequence {
            for (c in children) {
                yield(c)
                yieldAll(c.descendants())
            }
        }

        fun hasLabel() = text.isNotEmpty() || desc.isNotEmpty()

        fun firstText(): String = (sequenceOf(this) + descendants()).firstOrNull { it.hasLabel() }?.label ?: ""
    }

    class Win(val info: AccessibilityWindowInfo?, val z: Int, val bounds: Rect)

    /** 지금 화면 (아래 창 → 위 창 순서의 노드 목록). 키보드·상태 표시줄·내비게이션 바는 뺀다. */
    class Tree(val roots: List<Node>, val windows: List<Win>, val keyboard: Boolean) {
        fun all(): Sequence<Node> = roots.asSequence().flatMap { sequenceOf(it) + it.descendants() }
    }

    fun tree(): Tree {
        val wins = try { ua.windows } catch (e: Exception) { emptyList() }
        val roots = mutableListOf<Node>()
        val kept = mutableListOf<Win>()
        var keyboard = false
        // ua.windows는 위 창이 먼저 → 뒤집어서 위 창이 목록 끝에 오게 (iOS 덤프처럼 팝업이 끝에)
        for ((i, w) in wins.reversed().withIndex()) {
            when (w.type) {
                AccessibilityWindowInfo.TYPE_INPUT_METHOD -> { keyboard = true; continue }
                AccessibilityWindowInfo.TYPE_SYSTEM, AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY,
                AccessibilityWindowInfo.TYPE_SPLIT_SCREEN_DIVIDER -> continue
            }
            val root = w.root ?: continue
            val rect = Rect().also { w.getBoundsInScreen(it) }
            val win = Win(w, i, rect)
            kept += win
            roots += build(root, null, win, 0)
        }
        if (roots.isEmpty()) {
            ua.rootInActiveWindow?.let { r ->
                val win = Win(null, 0, screenRect)
                kept += win
                roots += build(r, null, win, 0)
            }
        }
        return Tree(roots, kept, keyboard)
    }

    private fun build(info: AccessibilityNodeInfo, parent: Node?, win: Win, depth: Int): Node {
        val node = Node(info, parent, win)
        if (depth < 120) {
            for (i in 0 until info.childCount) {
                val c = info.getChild(i) ?: continue
                node.children += build(c, node, win, depth + 1)
            }
        }
        node.type = typeOf(node)
        return node
    }

    // ───────────────────────────── 타입 (15_android.py android_type과 같게) ─────────────────────────────

    companion object {
        val TYPES = listOf(
            "EditText" to "TextField", "AutoCompleteTextView" to "TextField",
            "Switch" to "Switch", "SwitchCompat" to "Switch", "SwitchMaterial" to "Switch", "ToggleButton" to "Switch",
            "CheckBox" to "Switch", "RadioButton" to "Switch",
            "ImageButton" to "Button", "Button" to "Button", "FloatingActionButton" to "Button", "Chip" to "Button",
            "ImageView" to "Image", "TextView" to "StaticText",
            "RecyclerView" to "CollectionView", "GridView" to "CollectionView", "ViewPager" to "CollectionView",
            "ListView" to "Table", "ScrollView" to "ScrollView", "NestedScrollView" to "ScrollView",
            "WebView" to "WebView", "TabLayout" to "TabBar", "BottomNavigationView" to "TabBar",
            "NavigationBarView" to "TabBar",
        )

        fun shortId(rid: String): String {
            if (rid.isEmpty()) return ""
            val i = rid.indexOf(":id/")
            if (i < 0) return rid                       // Compose testTag (testTagsAsResourceId)
            val pkg = rid.substring(0, i)
            val name = rid.substring(i + 4)
            return if (pkg == "android") "android.$name" else name
        }

        fun typeOf(n: Node): String {
            val cls = n.cls.substringAfterLast('.')
            var t = TYPES.firstOrNull { cls.endsWith(it.first) }?.second ?: "Other"
            if (t == "TextField" && n.info.isPassword) t = "SecureTextField"
            if (t in listOf("Other", "StaticText", "Image") && n.clickable) {
                val labeled = (sequenceOf(n) + n.descendants()).count { it.hasLabel() }
                t = if (t == "Other" && labeled >= 2) "Cell" else "Button"
            }
            return t
        }

        fun typeName(name: String?): String? = when (name?.lowercase()) {
            null -> null
            "button" -> "Button"
            "cell" -> "Cell"
            "text", "statictext" -> "StaticText"
            "textfield" -> "TextField"
            "securetextfield" -> "SecureTextField"
            "switch" -> "Switch"
            "image" -> "Image"
            "other" -> "Other"
            "collectionview", "collection" -> "CollectionView"
            "scrollview", "scroll" -> "ScrollView"
            "table", "tableview" -> "Table"
            else -> null
        }
    }

    // ───────────────────────────── 상태 ─────────────────────────────

    /** 화면에 보이는 영역 (화면·창과 겹치는 부분). 없으면 빈 사각형. */
    fun visibleRect(n: Node): Rect {
        val r = Rect(n.bounds)
        if (!r.intersect(screenRect) || !r.intersect(n.window.bounds)) return Rect()
        return r
    }

    fun isVisible(n: Node): Boolean = n.visibleToUser && !visibleRect(n).isEmpty

    /** 보이고, 그 가운데를 위 창(팝업·대화상자·키보드 제외)이 덮지 않음 */
    fun isHittable(n: Node, tree: Tree): Boolean {
        if (!isVisible(n)) return false
        val r = visibleRect(n)
        return tree.windows.none { it.z > n.window.z && it.bounds.contains(r.centerX(), r.centerY()) }
    }

    fun foreground(): String? {
        val wins = try { ua.windows } catch (e: Exception) { emptyList() }
        val app = wins.firstOrNull { it.type == AccessibilityWindowInfo.TYPE_APPLICATION && it.root != null }
        return app?.root?.packageName?.toString() ?: ua.rootInActiveWindow?.packageName?.toString()
    }

    // ───────────────────────────── 조작 ─────────────────────────────

    fun tap(n: Node) {
        val r = visibleRect(n).takeUnless { it.isEmpty } ?: n.bounds
        device.click(r.centerX(), r.centerY())
    }

    fun swipe(n: Node, dir: String) {
        val r = visibleRect(n).takeUnless { it.isEmpty } ?: screenRect
        val dx = (r.width() * 0.35).toInt()
        val dy = (r.height() * 0.35).toInt()
        val (x1, y1, x2, y2) = when (dir) {
            "down" -> listOf(r.centerX(), r.centerY() - dy, r.centerX(), r.centerY() + dy)
            "left" -> listOf(r.centerX() + dx, r.centerY(), r.centerX() - dx, r.centerY())
            "right" -> listOf(r.centerX() - dx, r.centerY(), r.centerX() + dx, r.centerY())
            else -> listOf(r.centerX(), r.centerY() + dy, r.centerX(), r.centerY() - dy)
        }
        device.swipe(x1, y1, x2, y2, 12)   // 한 걸음 약 5ms → 빠른 쓸기 (iOS swipeUp과 비슷)
    }

    /** 두 손가락 핀치. scale > 1 확대(벌림), < 1 축소(오므림). 좌표 제스처라 요소 종류와 관계없다. */
    fun pinch(n: Node, scale: Double, steps: Int = 25) {
        val r = visibleRect(n).takeUnless { it.isEmpty } ?: screenRect
        val half = (minOf(r.width(), r.height()) * 0.42).toInt()
        val small = maxOf(40, (half / maxOf(scale, 1 / scale)).toInt())
        val (from, to) = if (scale >= 1) small to half else half to small
        val cx = r.centerX(); val cy = r.centerY()
        device.findObject(UiSelector()).performTwoPointerGesture(
            Point(cx - from, cy), Point(cx + from, cy), Point(cx - to, cy), Point(cx + to, cy), steps)
    }

    fun twoFingerTap(n: Node) {
        val r = visibleRect(n).takeUnless { it.isEmpty } ?: screenRect
        val cx = r.centerX(); val cy = r.centerY(); val d = (40 * density).toInt()
        device.findObject(UiSelector()).performTwoPointerGesture(
            Point(cx - d, cy), Point(cx + d, cy), Point(cx - d, cy), Point(cx + d, cy), 2)
    }

    /** 입력칸에 글자 넣기: 눌러서 포커스 → ACTION_SET_TEXT (한글도 그대로 들어간다). */
    fun setText(n: Node, value: String): Boolean {
        val target = (sequenceOf(n) + n.descendants()).firstOrNull { it.editable } ?: n
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value)
        }
        if (target.info.isFocused && target.info.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return true
        tap(target)
        // 누르면 포커스가 옮겨 가며 노드가 새로 만들어질 수 있다 → 지금 입력 포커스를 가진 칸에 넣는다
        val end = android.os.SystemClock.elapsedRealtime() + 2000
        while (android.os.SystemClock.elapsedRealtime() < end) {
            val focused = ua.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            if (focused != null && focused.isEditable && focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return true
            target.info.refresh()
            if (target.info.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return true
            android.os.SystemClock.sleep(200)
        }
        return false
    }

    fun screenshotPng(crop: Rect? = null): ByteArray? {
        val bmp = ua.takeScreenshot() ?: return null
        val shot = if (crop != null && !crop.isEmpty) {
            val c = Rect(crop).apply { intersect(0, 0, bmp.width, bmp.height) }
            Bitmap.createBitmap(bmp, c.left, c.top, c.width(), c.height())
        } else bmp
        return ByteArrayOutputStream().use { shot.compress(Bitmap.CompressFormat.PNG, 100, it); it.toByteArray() }
    }

    fun digest(bytes: ByteArray?): String =
        bytes?.let { MessageDigest.getInstance("SHA-1").digest(it).joinToString("") { b -> "%02x".format(b) } } ?: ""

    fun shell(cmd: String): String {
        val pfd = ua.executeShellCommand(cmd)
        return android.os.ParcelFileDescriptor.AutoCloseInputStream(pfd).use { it.readBytes().toString(Charsets.UTF_8) }
    }

    // ───────────────────────────── uiautomator 형식 XML (호스트가 덤프 텍스트로 바꾼다) ─────────────────────────────

    fun xml(tree: Tree = tree()): String {
        val sb = StringBuilder("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">")
        fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\"", "&quot;").replace("\n", "&#10;")
        fun write(n: Node, index: Int) {
            val b = n.bounds
            sb.append("<node index=\"$index\" text=\"${esc(n.text)}\" resource-id=\"${esc(n.resourceId)}\"")
            sb.append(" class=\"${esc(n.cls)}\" package=\"${esc(n.info.packageName?.toString() ?: "")}\"")
            sb.append(" content-desc=\"${esc(n.desc)}\" hint=\"${esc(n.hint)}\" checked=\"${n.info.isChecked}\"")
            sb.append(" clickable=\"${n.clickable}\" enabled=\"${n.enabled}\" scrollable=\"${n.info.isScrollable}\"")
            sb.append(" password=\"${n.info.isPassword}\" selected=\"${n.info.isSelected}\"")
            sb.append(" visible-to-user=\"${n.visibleToUser}\" bounds=\"[${b.left},${b.top}][${b.right},${b.bottom}]\">")
            n.children.forEachIndexed { i, c -> write(c, i) }
            sb.append("</node>")
        }
        tree.roots.forEachIndexed { i, r -> write(r, i) }
        return sb.append("</hierarchy>").toString()
    }
}
