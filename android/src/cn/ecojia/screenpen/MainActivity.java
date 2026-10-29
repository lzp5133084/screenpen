package cn.ecojia.screenpen;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/**
 * 主界面：权限引导 + 开启/关闭悬浮球。
 */
public class MainActivity extends Activity {

    private static final int GOLD_LIGHT = 0xFFF7E8BE;
    private static final int TEXT = 0xFFEDEFF3;
    private static final int DIM = 0xFF9AA0AC;

    private float dp;
    private TextView statusText;
    private TextView toggleBtn;

    /** 按钮点击 */
    private static class Click implements View.OnClickListener {
        private final MainActivity act;
        private final int action;

        Click(MainActivity a, int i) {
            act = a;
            action = i;
        }

        @Override
        public void onClick(View v) {
            if (action == 1) {
                act.openOverlaySettings();
            } else {
                act.toggleFloat();
            }
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        dp = getResources().getDisplayMetrics().density;

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(0xFF0A0B0F);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding((int) (20 * dp), (int) (28 * dp), (int) (20 * dp), (int) (24 * dp));
        scroll.addView(root);

        root.addView(title("鼠标画笔"));
        root.addView(note("安卓悬浮球版 · 在任意界面随时标注", 12, DIM, 6));

        LinearLayout card = card();
        statusText = note("", 13, TEXT, 0);
        card.addView(statusText);
        root.addView(card);

        root.addView(note("操作步骤", 13, GOLD_LIGHT, 20));

        TextView grant = button("① 授权悬浮窗权限", true);
        grant.setOnClickListener(new Click(this, 1));
        root.addView(grant);

        toggleBtn = button("② 开启悬浮球", false);
        toggleBtn.setOnClickListener(new Click(this, 2));
        root.addView(toggleBtn);

        root.addView(note("怎么用", 13, GOLD_LIGHT, 22));
        root.addView(note("1. 轻点金色悬浮球 → 进入标注模式，工具条出现在屏幕顶部。", 12, TEXT, 8));
        root.addView(note("2. 按住悬浮球可拖动到顺手的位置，程序会记住上次选的颜色和工具。", 12, TEXT, 6));
        root.addView(note("3. 选「画笔 / 荧光 / 直线 / 箭头 / 矩形 / 椭圆」后直接在屏幕上画。", 12, TEXT, 6));
        root.addView(note("4. 「橡皮」碰到的笔迹会被整笔擦掉，不会擦掉屏幕原本的画面。", 12, TEXT, 6));
        root.addView(note("5. 「穿透」＝标注层暂时让路，可以正常操作下面的 App，笔迹仍保留；再点一次回到绘画。", 12, TEXT, 6));
        root.addView(note("6. 「收起」回到只有悬浮球的状态，「退出」彻底关闭悬浮球。", 12, TEXT, 6));

        root.addView(note("名词解释", 13, GOLD_LIGHT, 22));
        root.addView(note("悬浮窗权限：系统级开关，允许本程序把一个小球和一层透明画布盖在其他 App 上面。", 12, DIM, 8));
        root.addView(note("标注层：一张铺满屏幕的透明纸，画的东西都在这张纸上，下面的 App 完全不受影响。", 12, DIM, 6));

        root.addView(note("v1.1.0 · 2026-10-29", 11, DIM, 26));
        root.addView(note("作者：军哥懂保　微信：xunijiayuan", 11, DIM, 4));

        setContentView(scroll);

        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 11);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private void refresh() {
        boolean granted = Settings.canDrawOverlays(this);
        boolean running = FloatService.running;
        statusText.setText((granted ? "已授权悬浮窗权限" : "未授权悬浮窗权限")
                + "\n" + (running ? "悬浮球正在运行" : "悬浮球未开启"));
        statusText.setTextColor(granted ? TEXT : 0xFFFFB386);
        toggleBtn.setText(running ? "关闭悬浮球" : "开启悬浮球");
    }

    private void openOverlaySettings() {
        Intent i = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + getPackageName()));
        startActivity(i);
    }

    private void toggleFloat() {
        if (FloatService.running) {
            stopService(new Intent(this, FloatService.class));
            Toast.makeText(this, "悬浮球已关闭", Toast.LENGTH_SHORT).show();
            refresh();
            return;
        }
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "请先授权「悬浮窗」权限", Toast.LENGTH_LONG).show();
            openOverlaySettings();
            return;
        }
        Intent i = new Intent(this, FloatService.class);
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(i);
        } else {
            startService(i);
        }
        Toast.makeText(this, "悬浮球已开启，回到桌面即可使用", Toast.LENGTH_LONG).show();
        moveTaskToBack(true);
    }

    // ------------------------------------------------------------ UI 小工具
    private TextView title(String s) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(26);
        t.setTextColor(GOLD_LIGHT);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setLetterSpacing(0.06f);
        return t;
    }

    private TextView note(String s, int size, int color, int topMargin) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(size);
        t.setTextColor(color);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = (int) (topMargin * dp);
        t.setLayoutParams(lp);
        t.setLineSpacing(4 * dp, 1.15f);
        return t;
    }

    private LinearLayout card() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (14 * dp);
        l.setPadding(pad, pad, pad, pad);
        l.setBackground(round(0xFF14161C, 0x33E8C87A, 14 * dp));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = (int) (18 * dp);
        l.setLayoutParams(lp);
        return l;
    }

    private TextView button(String s, boolean outline) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(14);
        t.setGravity(Gravity.CENTER);
        t.setTextColor(outline ? GOLD_LIGHT : 0xFF14161C);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding(0, (int) (13 * dp), 0, (int) (13 * dp));
        t.setBackground(round(outline ? 0x1AE8C87A : 0xFFE8C87A, 0xB3E8C87A, 12 * dp));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = (int) (10 * dp);
        t.setLayoutParams(lp);
        return t;
    }

    private GradientDrawable round(int fill, int stroke, float radius) {
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.RECTANGLE);
        g.setColor(fill);
        g.setCornerRadius(radius);
        if (Color.alpha(stroke) > 0) {
            g.setStroke((int) dp, stroke);
        }
        return g;
    }
}
