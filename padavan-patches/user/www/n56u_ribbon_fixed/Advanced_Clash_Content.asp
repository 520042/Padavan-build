<!DOCTYPE html>
<html>
<head>
<title><#Web_Title#> - Clash</title>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="-1">

<link rel="shortcut icon" href="images/favicon.ico">
<link rel="icon" href="images/favicon.png">
<link rel="stylesheet" type="text/css" href="/bootstrap/css/bootstrap.min.css">
<link rel="stylesheet" type="text/css" href="/bootstrap/css/main.css">
<link rel="stylesheet" type="text/css" href="/bootstrap/css/engage.itoggle.css">

<script type="text/javascript" src="/jquery.js"></script>
<script type="text/javascript" src="/bootstrap/js/bootstrap.min.js"></script>
<script type="text/javascript" src="/bootstrap/js/engage.itoggle.min.js"></script>
<script type="text/javascript" src="/state.js"></script>
<script type="text/javascript" src="/general.js"></script>
<script type="text/javascript" src="/itoggle.js"></script>
<script type="text/javascript" src="/popup.js"></script>
<script type="text/javascript" src="/help.js"></script>

<script>
<% clash_status(); %>

var $j = jQuery.noConflict();

$j(document).ready(function(){
	init_itoggle('clash_enable');
});

function initial(){
	show_banner(2);
	show_menu(5,15,1);
	show_footer();
	var o1 = document.form.clash_mode;
	var o2 = document.form.clash_core;
	o1.value = '<% nvram_get_x("","clash_mode"); %>';
	o2.value = '<% nvram_get_x("","clash_core"); %>';
	var o3 = $("autocron_sel");
	o3.value = '<% nvram_get_x("","clash_autocron"); %>';
	if (o3.value == '') o3.value = '0';
	fill_clash_status(clash_status());
	load_profiles();
	load_yaml();
}

function applyRule(){
	showLoading();
	document.form.action_mode.value = " Restart ";
	document.form.current_page.value = "Advanced_Clash_Content.asp";
	document.form.next_page.value = "";
	document.form.submit();
}

function submitInternet(v){
	showLoading();
	document.Clash_action.action = "Clash_action.asp";
	document.Clash_action.connect_action.value = v;
	if (v == 'SaveProfile')
		document.Clash_action.profile_name.value = $("profile_name").value;
	else if (v == 'LoadProfile' || v == 'DelProfile')
		document.Clash_action.profile_name.value = $("profile_list").value;
	else if (v == 'AutoCron')
		document.Clash_action.autocron_val.value = $("autocron_sel").value;
	document.Clash_action.submit();
}

function fill_clash_status(status_code){
	var stext = "Unknown";
	if (status_code == 0)
		stext = "<#Stopped#>";
	else if (status_code == 1)
		stext = "<#Running#>";
	$("clash_status").innerHTML = '<span class="label label-' + (status_code != 0 ? 'success' : 'warning') + '">' + stext + '</span>';
}

function load_profiles(){
	$j.get("Clash_cfg.asp", {type: "profiles"}, function(r){
		var list;
		try { list = (typeof r == 'string') ? JSON.parse(r) : r; } catch(e){ list = []; }
		var sel = $("profile_list");
		sel.innerHTML = '';
		if (!list || !list.length){
			var op = document.createElement('option');
			op.value = ''; op.text = '（暂无模式）';
			sel.appendChild(op);
			return;
		}
		for (var i = 0; i < list.length; i++){
			var op2 = document.createElement('option');
			op2.value = list[i]; op2.text = list[i];
			sel.appendChild(op2);
		}
	});
}

function load_yaml(){
	$j.get("Clash_cfg.asp", {type: "cfg"}, function(r){
		$("cfg_text").value = r;
	});
}

function save_yaml(){
	var txt = $("cfg_text").value;
	if (!txt || txt.length < 10){ alert('内容为空'); return; }
	$j.post("Clash_cfg.asp", {type: "cfg", cfg: txt}, function(r){
		alert(r);
	});
}

function check_yaml(){
	var txt = $("cfg_text").value;
	if (!txt || txt.length < 10){ alert('内容为空'); return; }
	$j.post("Clash_cfg.asp", {type: "cfg", cfg: txt, action: "check"}, function(r){
		if (r.indexOf("CONFIG OK") >= 0)
			alert('语法校验通过，核心可正常加载');
		else
			alert(r);
	});
}

function download_yaml(){
	var blob = new Blob([$("cfg_text").value], {type: "text/plain"});
	var a = document.createElement('a');
	a.href = URL.createObjectURL(blob);
	a.download = "clash-config.yaml";
	a.click();
	URL.revokeObjectURL(a.href);
}

function import_yaml(el){
	var f = el.files[0];
	if (!f) return;
	var rd = new FileReader();
	rd.onload = function(e){
		$("cfg_text").value = e.target.result;
		alert('已导入 ' + f.name + '，检查内容后点「校验并保存」');
	};
	rd.readAsText(f);
	el.value = '';
}

function restore_yaml(){
	if (!confirm('恢复上次备份（config.yaml.bak）并重启核心？')) return;
	$j.post("Clash_cfg.asp", {type: "cfg", action: "restore"}, function(r){
		alert(r);
		load_yaml();
	});
}

function reset_yaml(){
	if (!confirm('恢复出厂默认配置（wangka 免流结构）并重启核心？\n当前配置会自动备份为 config.yaml.bak')) return;
	$j.post("Clash_cfg.asp", {type: "cfg", action: "reset"}, function(r){
		alert(r);
		load_yaml();
	});
}

function refresh_status(){
	$j.get("Clash_cfg.asp", {type: "status"}, function(r){
		fill_clash_status(parseInt(r) || 0);
	});
}
setInterval(refresh_status, 5000);

</script>

<style>
.nav-tabs > li > a {
    padding-right: 6px;
    padding-left: 6px;
}
</style>
</head>

<body onload="initial();" onunLoad="return unload_body();">

<div class="wrapper">
    <div class="container-fluid" style="padding-right: 0px">
        <div class="row-fluid">
            <div class="span3"><center><div id="logo"></div></center></div>
            <div class="span9" >
                <div id="TopBanner"></div>
            </div>
        </div>
    </div>

    <div id="Loading" class="popup_bg"></div>

    <iframe name="hidden_frame" id="hidden_frame" src="" width="0" height="0" frameborder="0"></iframe>
    <form method="post" name="form" id="ruleForm" action="/start_apply.htm" target="hidden_frame">

    <input type="hidden" name="current_page" value="Advanced_Clash_Content.asp">
    <input type="hidden" name="next_page" value="">
    <input type="hidden" name="next_host" value="">
    <input type="hidden" name="sid_list" value="ClashConf;">
    <input type="hidden" name="group_id" value="">
    <input type="hidden" name="action_mode" value="">
    <input type="hidden" name="action_script" value="">

    <div class="container-fluid">
        <div class="row-fluid">
            <div class="span3">
                <!--Sidebar content-->
                <!--=====Beginning of Main Menu=====-->
                <div class="well sidebar-nav side_nav" style="padding: 0px;">
                    <ul id="mainMenu" class="clearfix"></ul>
                    <ul class="clearfix">
                        <li>
                            <div id="subMenu" class="accordion"></div>
                        </li>
                    </ul>
                </div>
            </div>

            <div class="span9">
                <!--Body content-->
                <div class="row-fluid">
                    <div class="span12">
                        <div class="box well grad_colour_dark_blue">
                            <h2 class="box_head round_top">Clash</h2>
                            <div class="round_bottom">
                                <div class="row-fluid">
                                    <div id="tabMenu" class="submenuBlock"></div>
                                    <table width="100%" cellpadding="4" cellspacing="0" class="table">
                                        <tr> <th colspan="2" style="background-color: #E3E3E3;">运行控制</th> </tr>

                                        <tr> <th><#running_status#></th>
                                            <td id="clash_status" colspan="3"></td>
                                        </tr>

                                        <tr> <th width="50%">核心操作</th>
                                            <td style="border-top: 0 none;" colspan="2">
                                                <input type="button" id="btn_clash_start" class="btn btn-info" value="启动" onclick="submitInternet('Start');">
                                                <input type="button" id="btn_clash_stop" class="btn btn-warning" value="停止" onclick="submitInternet('Stop');">
                                                <input type="button" id="btn_clash_restart" class="btn btn-primary" value="重启" onclick="submitInternet('Restart');">
                                                <input type="button" id="btn_clash_unblock" class="btn btn-danger" value="🛡解除断网" onclick="submitInternet('Unblock');">
                                            </td>
                                        </tr>

                                        <tr> <th>透明代理开关</th>
                                            <td>
                                                <div class="main_itoggle">
                                                    <div id="clash_enable_on_of">
                                                        <input type="checkbox" id="clash_enable_fake" <% nvram_match_x("", "clash_enable", "1", "value=1 checked"); %><% nvram_match_x("", "clash_enable", "0", "value=0"); %>>
                                                    </div>
                                                </div>

                                                <div style="position: absolute; margin-left: -10000px;">
                                                    <input type="radio" value="1" name="clash_enable" id="clash_enable_1" <% nvram_match_x("", "clash_enable", "1", "checked"); %>><#checkbox_Yes#>
                                                    <input type="radio" value="0" name="clash_enable" id="clash_enable_0" <% nvram_match_x("", "clash_enable", "0", "checked"); %>><#checkbox_No#>
                                                </div>
                                            </td>
                                        </tr>

                                        <tr> <th width="50%">运行模式</th>
                                            <td>
                                                <select name="clash_mode" class="input" style="width: 200px;">
                                                    <option value="rule" >Rule（规则分流）</option>
                                                    <option value="global" >Global（全局代理）</option>
                                                    <option value="direct" >Direct（全局直连）</option>
                                                </select>
                                            </td>
                                        </tr>

                                        <tr> <th width="50%">核心选择</th>
                                            <td>
                                                <select name="clash_core" class="input" style="width: 200px;">
                                                    <option value="mihomo" >mihomo（Meta 内核，推荐）</option>
                                                    <option value="classic" >经典 clash（内置 v1.18.0）</option>
                                                </select>
                                            </td>
                                        </tr>

                                        <tr> <th colspan="2" style="background-color: #E3E3E3;">订阅管理</th> </tr>

                                        <tr> <th width="50%">订阅链接</th>
                                            <td>
                                                <input type="text" maxlength="255" class="input" size="64" name="clash_sub_url" value="<% nvram_get_x("","clash_sub_url"); %>" />
                                            </td>
                                        </tr>

                                        <tr> <th width="50%">订阅名称（备注）</th>
                                            <td>
                                                <input type="text" maxlength="64" class="input" size="32" name="clash_sub_name" value="<% nvram_get_x("","clash_sub_name"); %>" />
                                            </td>
                                        </tr>

                                        <tr>
                                            <th width="50%">更新订阅</th>
                                            <td style="border-top: 0 none;" colspan="2">
                                                <input type="button" id="btn_clash_sub" class="btn btn-info" value="拉取订阅并重启核心" onclick="submitInternet('Update_sub');">
                                            </td>
                                        </tr>

                                        <tr>
                                            <th width="50%">订阅自动更新</th>
                                            <td>
                                                <select id="autocron_sel" class="input" style="width: 200px;">
                                                    <option value="0">关闭</option>
                                                    <option value="1">每 1 小时</option>
                                                    <option value="2">每 2 小时</option>
                                                    <option value="3">每 3 小时</option>
                                                    <option value="6">每 6 小时</option>
                                                    <option value="12">每 12 小时</option>
                                                    <option value="24">每 24 小时</option>
                                                </select>
                                                <input type="button" class="btn btn-info" value="保存" onclick="submitInternet('AutoCron');">
                                            </td>
                                        </tr>

                                        <tr> <th colspan="2" style="background-color: #E3E3E3;">模式管理</th> </tr>

                                        <tr> <th width="50%">保存当前配置为模式</th>
                                            <td>
                                                <input type="text" maxlength="32" class="input" size="24" id="profile_name" placeholder="模式名（字母/数字/_/-）">
                                                <input type="button" class="btn btn-info" value="保存" onclick="submitInternet('SaveProfile');">
                                            </td>
                                        </tr>

                                        <tr> <th width="50%">已存模式（加载会自动重启核心）</th>
                                            <td>
                                                <select id="profile_list" class="input" style="width: 200px;"></select>
                                                <input type="button" class="btn btn-primary" value="加载" onclick="submitInternet('LoadProfile');">
                                                <input type="button" class="btn btn-danger" value="删除" onclick="submitInternet('DelProfile');">
                                                <input type="button" class="btn" value="刷新列表" onclick="load_profiles();">
                                            </td>
                                        </tr>

                                        <tr> <th colspan="2" style="background-color: #E3E3E3;">YAML 配置编辑器</th> </tr>

                                        <tr> <td colspan="2">
                                            <textarea id="cfg_text" class="input" rows="12" style="width: 95%; font-family: monospace;" spellcheck="false"></textarea><br>
                                            <input type="button" class="btn" value="重新加载" onclick="load_yaml();">
                                            <input type="button" class="btn btn-warning" value="仅校验" onclick="check_yaml();">
                                            <input type="button" class="btn btn-primary" value="校验并保存" onclick="save_yaml();">
                                            <input type="button" class="btn btn-info" value="保存并重启核心" onclick="save_yaml(); submitInternet('Restart');">
                                            <input type="button" class="btn" value="下载 yaml" onclick="download_yaml();">
                                            <input type="button" class="btn" value="导入 yaml 文件" onclick="$('cfg_file').click();">
                                            <input type="file" id="cfg_file" style="display:none" accept=".yaml,.yml,.txt" onchange="import_yaml(this);">
                                            <input type="button" class="btn btn-danger" value="恢复备份" onclick="restore_yaml();">
                                            <input type="button" class="btn btn-danger" value="恢复出厂默认" onclick="reset_yaml();">
                                            <br><span style="margin-left: 10px; color: #888;">保存至 /etc/storage/clash/config.yaml（原文件自动备份为 .bak）</span>
                                        </td></tr>

                                        <tr>
                                            <td colspan="2">
                                                <center><input class="btn btn-primary" style="width: 219px" type="button" value="<#CTL_apply#>" onclick="applyRule()" /></center>
                                            </td>
                                        </tr>

                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</form>
<div id="footer"></div>
</div>

<form method="post" name="Clash_action" action="">
    <input type="hidden" name="connect_action" value="">
    <input type="hidden" name="profile_name" value="">
    <input type="hidden" name="autocron_val" value="">
</form>


</body>
</html>
