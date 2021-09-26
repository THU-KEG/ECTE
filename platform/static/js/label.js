var HH = 0; //时
var mm = 0; //分
var ss = 0; //秒
var timeState = true; //时间状态 默认为true 开启时间
var questions = [];
var itemList = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S"];
var activeQuestion = 0; //当前操作的考题编号
var checkQues = []; //已做答的题的集合
var g_sememe_str_now = '';
var g_test_type = 0;
var g_now_group_id = 0;
var g_now_test_period = 0;
var DISPALY_STATUS = {
    "DEFAULT": 0,
    "CONFIRM_SUBMIT": 1,
    "NEXT_OR_RETURN": 2
};
var g_is_error_state = false;

var status_now = DISPALY_STATUS.DEFAULT;
var start_time_flag = 0;

var lastparams = null;


var treedata;

/*实现计时器*/
var time = setInterval(function() {
    if (timeState) {
        if (HH == 24) HH = 0;
        str = "";
        if (++ss == 60) {
            if (++mm == 60) {
                HH++;
                mm = 0;
            }
            ss = 0;
        }
        str += HH < 10 ? "0" + HH : HH;
        str += ":";
        str += mm < 10 ? "0" + mm : mm;
        str += ":";
        str += ss < 10 ? "0" + ss : ss;
        $(".time").text(str);
    } else {
        $(".time").text(str);
    }

    start_time_flag += 1;
    if(start_time_flag >= 2){
        checkQues[activeQuestion].cost_time += 0.1;
        checkQues[activeQuestion].cost_time = eval(checkQues[activeQuestion].cost_time.toFixed(2));
    }
}, 100);

// Display a group of leveled taxonomy choices in one page
function showTaxonomies(q_data) {
    let group_name = "taxnomies"
    let hypernyms = q_data.map(x => x.hypernym).concat(["以上都不正确"]);
    for (const [id, hypernym] of hypernyms.entries()) {
        let taxonomy_choice = `<label><input name="${group_name}" type="radio" id="taxonomy_choice${id+1}" onclick="updateAnswerFromTaxonomies(${id})"/>${hypernym} </label><br>`;
        $(".taxonomy_choices").append(taxonomy_choice)
    }
}


function showTree(id){

    var mychart = echarts.init(
        document.getElementById('tree'), 'white', {renderer: 'canvas'});

    console.log(treedata)

    var myoption = {
    "hoverAnimation": true,
    "animation": true,
    "animationThreshold": 2000,
    "animationDuration": 1000,
    "animationEasing": "cubicOut",
    "animationDelay": 0,
    "animationDurationUpdate": 300,
    "animationEasingUpdate": "cubicOut",
    "animationDelayUpdate": 0,
    "color": [
    "#c23531",
    "#2f4554",
    "#61a0a8",
    "#d48265",
    "#749f83",
    "#ca8622",
    "#bda29a",
    "#6e7074",
    "#546570",
    "#c4ccd3",
    "#f05b72",
    "#ef5b9c",
    "#f47920",
    "#905a3d",
    "#fab27b",
    "#2a5caa",
    "#444693",
    "#726930",
    "#b2d235",
    "#6d8346",
    "#ac6767",
    "#1d953f",
    "#6950a1",
    "#918597"
    ],
    "tooltip": {
        "trigger": "item",
        "triggerOn": "mousemove",
        "axisPointer": {
            "type": "line"
        },
        "textStyle": {
            "fontSize": "100%"
        },
        "borderWidth": 0,

    },
    "series": [
    {
        "id": id,
        "type": "tree",
        "data": treedata,
        "top": "10%",
        "bottom": "15%",
        "right": "50%",
        "left": "15%",
        "height": "80%",
        "width": "80%",
        "symbol": "emptyCircle",
        "symbolSize": 15,
        "expandAndCollapse": true,
        "layout": "orthogonal",
        "orient": "LR",
        "initialTreeDepth": 4,
        "roam": true,
        "label": {
            "normal": {
            "position": 'middle',
            "verticalAlign": 'middle',
            "align": 'right',
            "fontSize": "100%",
            },
            "show": true,
            "position": "top",
            "margin": "100%"
        },
        "leaves": {
                "show": true,
                "position": "top",
                "margin": "100",
                "label": {
                    "normal": {
                        "position": 'left',
                        "verticalAlign": 'middle',
                        "align": 'right',
                        "fontSize": "100%",
                    }
                },

        },

    }
    ],

    };
    mychart.setOption(myoption);

    mychart.on('click', function (params) {
        if (lastparams != null){
            lastparams.data.symbol = 'emptyCircle';
        }
        params.data.symbol = 'rect';
        console.log(params.data.path);
        checkQues[params.seriesId].answer = params.data.path;
        lastparams = params;
    });

}


function loadNode(q_data) {
    let nodename = q_data[0].hypernym;
    // nodename = "flare/analytics/cluster";
    let words = nodename.split("/");
    traverseTree(treedata, words, 0);

}

function traverseTree(root, words, num) {
    if (num == words.length) {
        return;
    }

    for (let i = 0; i < root.length; i++) {
        if (root[i] != null) {
            if (root[i].name == words[num]) {
                root[i].mcHereShow = true;
                traverseTree(root[i].children, words, num+1);
                return;
            }
        }
    }
}


function updateAnswerFromTaxonomies(id) {
    if (id === checkQues.length) {
        for (let item of checkQues) {
            item.answer = 0
        }
    } else {
        for (let [item_id, item] of checkQues.entries()) {
            if (item_id === id) {
                item.answer = 1
            } else {
                item.answer = 0
            }
        }
    }
    console.log(checkQues)
}

//展示考卷信息
function showQuestion(id) {
    if (activeQuestion != undefined) {
        $("#ques" + activeQuestion).removeClass("question_id").addClass("active_question_id");
    } // 把当前选中的题目的题号方框加上已经过选择过的类型
    activeQuestion = id;
    $(".question").find(".question_info").remove(); //移除所有选项
    // var items = ['是(y)', '否(n)'];

    console.log("q_data: ")
    console.log(q_data)

    var hyponym = q_data[id].hyponym;
    var display = "<p style=\"font-size: 20px\">" + "子类别： <strong>" + `<a href="https://www.baidu.com/s?wd=${hyponym}" target="_blank">${hyponym}</a>` + "</strong><br> <p style=\"font-size: 15px\">请选择<b>最细粒度</b>的分类</p>";
    $(".question_title").html(display); // 显示题目信息

    if(g_test_type == 1 && g_is_error_state == true){
        $("#test_answer").html('【解析】' + q_data[id].explaint);
    }
    // // 选项卡
    // for (var i = 0; i < items.length; i++) {
    //     item = "<li class='question_info ' onclick='clickTrim(this)' id='item" + i + "'><input type='hidden' name='item' value='" + itemList[i] + "'>&nbsp;" + itemList[i] + "." + items[i] + "</li>";
    //     $(".question").append(item); // 显示题目的选项
    // }
    $(".question").attr("id", "question" + id); // 设置题目的id
    $("#ques" + id).removeClass("active_question_id").addClass("question_id"); // 设置把当前题目的答题卡题号方框
    //跳转到的题目如果之前做过，那么把之前做的选项显示出来
    if (checkQues[id].item.length > 0) {
        for (var i = 0; i < checkQues[id].item.length; i++) {
            $("#" + checkQues[id].item[i]).find("input").prop("checked", "checked");
            $("#" + checkQues[id].item[i]).addClass("btn-primary");
        }
        $("#ques" + activeQuestion).removeClass("question_id").addClass("clickQue");
    }
}


var Question;

function clickTrim(source) {
    var id = source.id;
    if ($("#" + id).find("input").prop("checked") == true) { // 取消选中
        $("#" + id).find("input").prop("checked", false);
        $("#" + id).removeClass("btn-primary");
        checkQues[activeQuestion].answer = -1;

    } else {
        $("#" + id).find("input").prop("checked", "checked"); // 把被选中的选项设置为对勾
        $("#" + id).addClass("btn-primary");
        if ($(".question_info:last").attr("id") == id) { // 如果选中的是“都不合适”，则把其他所有选项都去掉
            $(".question_info").each(function() { // 遍历每个选项
                var otherId = $(this).attr("id"); // 被遍历的选项的ID
                if (otherId != id) { // 取消其他选项的对勾
                    $("#" + otherId).find("input").prop("checked", false);
                    $("#" + otherId).removeClass("btn-primary");
                }
            })
        } else { // 如果选择了其他选项，那么把都不合适选项要去掉
            $(".question_info:last").find("input").prop("checked", false);
            $(".question_info:last").removeClass("btn-primary");
        }
    }
    // 判断当前已经选中了哪几个选项
    var checkedItems = [];
    $(".question_info").each(function() { // 遍历每个选项
        var itemId = $(this).attr("id"); // 被遍历的选项的ID
        if ($(this).find("input").prop("checked") == true) {
            checkedItems.push(itemId);
        }
    })
    //改变当前题目的题号方框的样式
    if (checkedItems.length == 0) {
        $("#ques" + activeQuestion).removeClass("clickQue").addClass("question_id");
    } else {
        $("#ques" + activeQuestion).removeClass("question_id").addClass("clickQue");
    }
    // 存储答案
    checkQues[activeQuestion].item = checkedItems;
    checkQues[activeQuestion].answer = 1 - eval(checkedItems[0][4]);
    // // console.log(checkedItems[0][4])
    // // console.log(checkQues[activeQuestion].answer);
    Question = activeQuestion;
    setTimeout("$('#nextQuestion').click()", 200);
}
/*保存考题状态 已做答的状态*/
function saveQuestionState(clickId) { // 在答题卡上点击某道题可以跳转
    showQuestion(clickId)
    // $('.sememe').mouseenter();
}

//处理后端返回的problem数据
function process_problem(q_data) {
    return q_data;
}




// 主函数：当 DOM（文档对象模型） 已经加载，并且页面（包括图像）已经完全呈现时，会发生 ready 事件
$(function() {
    $.ajax({
        type: "get",
        url: "/static/science_class.json",
        dataType: "json",
        async: false,
        success: function(result){
            treedata = result
        }
    });
    $(".middle-top-left").width($(".middle-top").width() - $(".middle-top-right").width());
    g_test_type = $('#q_type').attr('value');
    //标注结束
    if($('#q_data').attr('value') == 'END'){
        if(g_test_type != 1)
            alert("感谢您的努力，您的标注任务已结束");
        else
            alert("您的测试已结束，请进行正式标注");
        location.href = "/";
    }
    console.log("q_data:")
    console.log($('#q_data').attr('value'))
    q_data = eval($('#q_data').attr('value'));
    $('#q_data').remove();
    q_data = process_problem(q_data);
    console.log("q_data:")
    console.log(q_data)
    // 初始化答案信息
    for (var i = 0; i < q_data.length; i++) {
        var answerTMP = {};
        answerTMP.id = i; //获取当前考题的编号
        answerTMP.actualId = q_data[i].id;
        answerTMP.item = []; //获取当前考题的选项ID
        answerTMP.answer = "";
        // answerTMP.NO = q_data.b_id;
        answerTMP.cost_time = 0.0;
        answerTMP.group_id = q_data[i].problem_group_id;
        checkQues.push(answerTMP);
    }
    //showTaxonomies(q_data);


    loadNode(q_data);
    showTree(0);
    showQuestion(0); // 显示第一题
    /*实现进度条信息加载的动画*/
    var str = '';
    /*开启或者停止时间*/
    $(".time-stop").click(function() {
        timeState = false;
        $(this).hide();
        $(".time-start").show();
    });
    $(".time-start").click(function() {
        timeState = true;
        $(this).hide();
        $(".time-stop").show();
    });
    /*答题卡的切换*/
    // $("#openCard").click(function() {
    //     $("#closeCard").show();
    //     $("#answerCard").slideDown();
    //     $(this).hide();
    // })
    // $("#closeCard").click(function() {
    //     $("#openCard").show();
    //     $("#answerCard").slideUp();
    //     $(this).hide();
    // })

    //展示状态的转换，
    $('#myModal').on('show.bs.modal', function () {
            //用户正在confirm submit
            status_now = DISPALY_STATUS.CONFIRM_SUBMIT;
    });
    $('#myModal').on('hide.bs.modal', function () {
            //正在答题
            status_now = DISPALY_STATUS.DEFAULT;
    });
    $('#myModal2').on('show.bs.modal', function () {
            //正在选择下一步还是返回
            status_now = DISPALY_STATUS.NEXT_OR_RETURN;
    });
    // 当弹出的模态框消失时触发的事件
    $('#myModal2').on('hide.bs.modal', function () {
            status_now = DISPALY_STATUS.DEFAULT;
    });

    $("#quitQuestions").click(function() {
        var problem_no_finish = false;
        for(var i = 0; i < checkQues.length; i++){
            if(checkQues[i].answer == -1){
                alert("第" + i +"题未作答");
                problem_no_finish = true;
                break;
            }
            checkQues[i].hyponym = q_data[0].hyponym;
            checkQues[i].hypernym = q_data[0].hypernym;
            checkQues[i].number = q_data[0].number;
            checkQues[i].round = q_data[0].round;
        }
        if(problem_no_finish){
            setTimeout(function(){
                $('#myModal4').modal('hide');
            },100);
            return;
        }
        $("#submitTip2").empty();
        $("#submitTip2").append("是否确定提交，并退出？");
    });

    $("#cancelSubmit2").click(function() {
        //模态框消失
        $('#myModal4').modal('hide');

    });

    //提交试卷
    $("#submitQuestions").click(function() {
        var problem_no_finish = false;
        for(var i = 0; i < checkQues.length; i++){
            if(checkQues[i].answer == -1){
                alert("第" + i +"题未作答");
                problem_no_finish = true;
                break;
            }
            checkQues[i].hyponym = q_data[0].hyponym;
            checkQues[i].hypernym = q_data[0].hypernym;
            checkQues[i].number = q_data[0].number;
            checkQues[i].round = q_data[0].round;
        }
        if(problem_no_finish){
            setTimeout(function(){
                $('#myModal').modal('hide');
            },100);
            return;
        }
        var data = JSON.stringify(checkQues);

        $("#submitTip").empty();
        $("#submitTip").append("是否确定标注无误，确认提交？");


    });
    $("#cancelSubmit").click(function() {
        //模态框消失
        $('#myModal').modal('hide');

    });

    $("#confirmSubmit2").click(function() {
        var data = JSON.stringify(checkQues);
        var post_url = '/answer';
        if (g_test_type == 1) {
            location.href = "/";
            return;
        }


        $.ajax({
            type: 'POST',
            url: post_url,
            data: data,
            dataType: 'text',
            async: false, // 注意这里改为异步才能成功赋值！
            success: function(data) {

                //后端传回重复发送的状态码
                if(data == '2'){
                    alert("请不要重复发送");
                }
                location.href = "/";
            },
            error: function(XMLResponse) {
                alert('提交失败，请重试');
            }

        });
    })

    $("#confirmSubmit").click(function() {
        var data = JSON.stringify(checkQues);
        var post_url = '/answer';
        if (g_test_type == 1) post_url = '/test'

        $.ajax({
            type: 'POST',
            url: post_url,
            data: data,
            dataType: 'text',
            async: false, // 注意这里改为异步才能成功赋值！
            success: function(data) {

                if (g_test_type == 1) {

                    var ans = data.split(' ');
                    var state = ans[0];
                    var corr_num = ans[1];
                    g_now_test_period = ans[2];
                    var incorrect_anwser = [];
                    if(state == 0){
                        for(var i = 3; i < ans.length; i++){
                            incorrect_anwser.push(ans[i]);
                        }
                        alert('共答对' + corr_num + '题\n' + incorrect_anwser + '号题错误，请重试');
                        g_is_error_state = true;
                        for(var j = 0; j < incorrect_anwser.length; j++){
                            showQuestion(j);
                        }

                        //location.reload("GET");
                    }else if(state == 1){
                        alert('恭喜全部正确，请进行下一组测试');
                        location.reload("GET");
                    }else{
                        alert('恭喜您通过全部测试');
                        location.href = "/";
                    }
                } else {
                    //后端传回重复发送的状态码
                    if(data == '2'){
                        alert("请不要重复发送");
                    }

                    location.reload("GET");
                }
            },
            error: function(XMLResponse) {
                alert('提交失败，请重试');
            }
        });
        $("#refresh").click(function() {
            location.reload("GET");
        });
        $("#returnToIndex").click(function() {
            location.href = "/";
        })
    })
    $("#post_feedback").click(function() {
        var data = {}
        data['problem_group_id'] = checkQues[activeQuestion].group_id;
        data['content'] = $('#error')[0].value;
        var post_data = JSON.stringify(data);
        var post_url = '/feedback';
        $.ajax({
            type: 'POST',
            url: post_url,
            data: post_data,
            dataType: 'json',
            async: false, // 注意这里改为异步才能成功赋值！
            success: function(data) {
                alert('提交成功');
                $("#myModal3").modal("hide");
            },
            error: function(XMLResponse) {
                alert('提交失败，请重试')
            }
        });
        $("#refresh").click(function() {
            location.reload("GET");
        });
        $("#returnToIndex").click(function() {
            location.href = "/"
        })
    })
    // 相当于下一组
    $("#refresh_problem").click(function() {
        var data = JSON.stringify(checkQues[0]);
        var post_url = '/skip';
        if (g_test_type == 1) post_url = '/test'
        $.ajax({
            type: 'POST',
            url: post_url,
            data: data,
            dataType: 'text',
            async: false, // 注意这里改为异步才能成功赋值！
            success: function (data) {
                location.reload("GET");
            },
            error: function (_) {
                location.reload("GET");
            }
        });
    })
    $("#openCard").click();
    $(document).keydown(function(event) {
        switch (event.keyCode) {
            //右键
            case 0x27:
                if(status_now == DISPALY_STATUS.DEFAULT)
                    $('#nextQuestion').click();
                break;
            //左键
            case 0x25:
                if(status_now == DISPALY_STATUS.DEFAULT)
                    $('#lastQuestion').click();
                break;
            //y
            case 89:
                switch (status_now) {
                    case DISPALY_STATUS.DEFAULT:
                        $('#submitQuestions').click();
                        break;
                    case DISPALY_STATUS.CONFIRM_SUBMIT:
                        $("#confirmSubmit").click();
                        break;
                }
                break;

            //n
            case 78:
                switch (status_now) {
                    case DISPALY_STATUS.DEFAULT:
                        $('#item1').click();
                        break;
                    case DISPALY_STATUS.CONFIRM_SUBMIT:
                        $("#myModal").modal("hide");
                        break;
                    case DISPALY_STATUS.NEXT_OR_RETURN:
                        $("#returnToIndex").click();
                        break;
                }
                break;

            // 1, 2, 3, 4
            case 49:
            case 50:
            case 51:
            case 52:
                switch (status_now) {
                    case DISPALY_STATUS.DEFAULT:
                        $(`#taxonomy_choice${event.keyCode - 48}`).click();
                        break;
                }
                break;

            // numpad 1, 2, 3, 4
            case 97:
            case 98:
            case 99:
            case 100:
                switch (status_now) {
                    case DISPALY_STATUS.DEFAULT:
                        $(`#taxonomy_choice${event.keyCode - 96}`).click();
                        break;
                }
                break;
        }
    })
});
