makePostCall = function (url, data) { // here the data and url are not hardcoded anymore
   var json_data = JSON.stringify(data);
	// console.log("QERY "+url);
	//console.log(json_data);
    return $.ajax({
        type: "GET",
        url: url,
        data: data,
        dataType: "json",
        contentType: "application/json;charset=utf-8"
    });
	
}

function recheck() {
	var me = $("#member_email")[0];
	var rc = $("#recheck_status");
	rc.removeClass("glyphicon-time");
	rc.removeClass("glyphicon-ok");
	rc.removeClass("glyphicon-remove");
	rc[0].setAttribute("style","color:black");
	if (me.value == "") {
		rc[0].innerHTML="Invalid";
		rc.addClass("glyphicon-remove");
		return;
	} 
	rc.addClass("glyphicon-time");
	rc[0].innerHTML="Checking...";
	makePostCall(GOOGLE_ACCT_CHECK_URL+me.value, null)
			.success(function(indata){
			console.log(indata);
				var rc = $("#recheck_status");
				rc.removeClass("glyphicon-time");
				rc.removeClass("glyphicon-ok");
				rc.removeClass("glyphicon-remove");
				if (indata.status == "error") {
					rc.addClass("glyphicon-remove");
					rc[0].setAttribute("style","color:red");
					rc[0].innerHTML="Error";
				} 
				else if (indata.status == "available") {
					rc.addClass("glyphicon-ok");
					rc[0].setAttribute("style","color:green");
					rc[0].innerHTML="Available";
				}
				else if (indata.status == "in-use") {
					rc.addClass("glyphicon-remove");
					rc[0].setAttribute("style","color:red");
					rc[0].innerHTML="In-Use";
				}
				else {
					rc.addClass("glyphicon-remove");
					rc[0].setAttribute("style","color:black");
					rc[0].innerHTML="Unknown";
				}
		 })
			.fail(function(sender, message, details){
				var rc = $("#recheck_status");
				rc.removeClass("glyphicon-time");
				rc.removeClass("glyphicon-ok");
				rc.removeClass("glyphicon-remove");
				rc.addClass("glyphicon-remove");
				rc[0].setAttribute("style","color:red");
				rc[0].innerHTML="Internal Error";
		});
}


function doPageLoad() {
	var rc = $("#recheck_status")[0];
	rc.innerHTML="Page Loaded";
	recheck();
}

$(document).ready(function() {
	doPageLoad();
});
