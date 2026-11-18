var lastrequest = null;

function layout_search_keypress() {
	var line = $("#layout_search_text").val() || "";
	if (line.length < 3) {
		$('#layout_search_menu').removeClass('open show');
		$('#layout_search_menu').parent().removeClass('open show');
		return;
	}

	makePostCall = function (url, data) {
		if (lastrequest != null) {
			lastrequest.abort();
			lastrequest = null;
		}
		var req = $.ajax({
			type: "GET",
			url: url,
			data: data,
			dataType: "json",
			contentType: "application/json;charset=utf-8"
		});
		lastrequest = req;
		return req;
	};

	makePostCall(LAYOUT_SEARCH_URL + encodeURIComponent(line), "")
		.done(function(data) {
			lastrequest = null;
			var lst = $("#layout_search_menu");
			lst.empty();

			if (data && data.length > 0) {
				for (var i = 0; i < data.length; i++) {
					var item = data[i];
					var el = document.createElement("a");
					el.style = 'cursor: pointer;';
					el.href = item['url'];
					el.className = "dropdown-item content layout_search_item nav-item nav-link";
					if (item['in']) {
						el.innerHTML = item['title'] + "<br /><small>" + item['in'] + "</small>";
					} else {
						el.innerHTML = item['title'];
					}
					lst.append(el);
				}
				lst.addClass('show');
				lst.parent().addClass('show');
			} else {
				lst.removeClass('open show');
				lst.parent().removeClass('open show');
			}
		})
		.fail(function(sender, message, details) {
			if (message !== "abort") {
				console.error("Ubersearch failed:", message, details);
			}
		});
}

function layout_search_blur() {
	setTimeout(function() {
		$('#layout_search_menu').removeClass('open show');
		$('#layout_search_menu').parent().removeClass('open show');
	}, 250);
}
